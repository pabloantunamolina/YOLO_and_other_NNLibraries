import os
import numpy as np
from tqdm import trange

import nnabla as nn
import nnabla.solvers as S
import nnabla.functions as F
from nnabla.logger import logger

from models import LocalGenerator, Discriminator, encode_inputs, define_loss
from utils import LearningRateScheduler, Reporter, Colorize
from data_iterator.data_loader import create_data_iterator


def get_params_startswith(str, ignore_in=True):
    # ignore instance_norm params
    # load_parameter() doesn`t consider as_need_grad and fix_parameter doesn't work well.
    params = nn.get_parameters()
    if ignore_in:
        params = {k: v for k, v in params.items() if k.split(
            "/")[-2] != "instance_normalization"}

    return {k: v for k, v in params.items() if k.startswith(str)}


class Trainer(object):
    def __init__(self, batch_size, base_image_shape, data_list,
                 max_epoch, learning_rate, comm, fix_global_epoch,
                 d_n_scales, g_n_scales, n_label_ids,
                 use_encoder=False, load_path=None, save_path=None, rng=None, is_data_flip=True):
        rng = np.random.RandomState(313) if rng is None else rng

        self.batch_size = batch_size
        self.image_shape = tuple(x * g_n_scales for x in base_image_shape)
        self.data_iter = create_data_iterator(batch_size, data_list,
                                              image_shape=self.image_shape, rng=rng, flip=is_data_flip)
        if comm.n_procs > 1:
            self.data_iter = self.data_iter.slice(
                rng, num_of_slices=comm.n_procs, slice_pos=comm.rank)
        self.max_epoch = max_epoch
        self.learning_rate = learning_rate
        self.comm = comm
        self.fix_global_epoch = max(fix_global_epoch, 0)
        self.d_n_scales = d_n_scales
        self.g_n_scales = g_n_scales
        self.n_label_ids = n_label_ids
        self.use_encoder = use_encoder
        self.load_path = load_path
        self.save_path = save_path

    def train(self):
        real = nn.Variable(shape=(self.batch_size, 3) + self.image_shape)
        inst_label = nn.Variable(shape=(self.batch_size, ) + self.image_shape)
        id_label = nn.Variable(shape=(self.batch_size, ) + self.image_shape)

        id_onehot, bm = encode_inputs(
            inst_label, id_label, n_ids=self.n_label_ids, use_encoder=self.use_encoder)
        bm.persistent = True

        x = F.concatenate(id_onehot, bm, axis=1)

        # generator
        # Note that only global generator would be used in the case of g_scales = 1.
        generator = LocalGenerator()
        fake, _, = generator(x, self.g_n_scales)
        fake.persistent = True
        unlinked_fake = fake.get_unlinked_variable(need_grad=True)

        # discriminator
        discriminator = Discriminator()

        d_input_real = F.concatenate(real, x, axis=1)
        d_input_fake = F.concatenate(unlinked_fake, x, axis=1)
        d_real_out, d_real_feats = discriminator(d_input_real, self.d_n_scales)
        d_fake_out, d_fake_feats = discriminator(d_input_fake, self.d_n_scales)

        g_gan, g_feat, g_vgg, d_real, d_fake = define_loss(d_real_out, d_real_feats,
                                                           d_fake_out, d_fake_feats, use_fm=True)

        g_gan.persistent = True
        g_feat.persistent = True
        g_vgg.persistent = True
        d_real.persistent = True
        d_fake.persistent = True

        g_loss = g_gan + g_feat + g_vgg
        d_loss = 0.5 * (d_real + d_fake)

        # load parameters
        if self.load_path:
            if not os.path.exists(self.load_path):
                logger.warn("Path to load params is not found."
                            " Loading params is skipped. ({})".format(self.load_path))
            else:
                nn.load_parameters(self.load_path)

        # Setup Solvers
        g_solver = S.Adam(beta1=0.5)
        g_solver.set_parameters(get_params_startswith("generator/local"))

        d_solver = S.Adam(beta1=0.5)
        d_solver.set_parameters(get_params_startswith("discriminator"))

        # lr scheduler
        lr_schduler = LearningRateScheduler(self.learning_rate, self.max_epoch)

        # Setup Reporter
        losses = {"g_gan": g_gan, "g_feat": g_feat,
                  "g_vgg": g_vgg, "d_real": d_real, "d_fake": d_fake}
        reporter = Reporter(self.comm, losses, self.save_path)

        # for label2color
        label2color = Colorize(self.n_label_ids)

        for epoch in range(self.max_epoch):
            if epoch == self.fix_global_epoch:
                g_solver.set_parameters(get_params_startswith(
                    "generator"), reset=False, retain_state=True)

            # update learning rate for current epoch
            lr = lr_schduler(epoch)
            g_solver.set_learning_rate(lr)
            d_solver.set_learning_rate(lr)

            progress_iterator = trange(self.data_iter._size // self.data_iter._batch_size,
                                       desc="[epoch {}]".format(epoch),
                                       disable=self.comm.rank > 0)

            reporter.epoch_start(epoch, progress_iterator)

            for i in progress_iterator:
                image, instance_id, object_id = self.data_iter.next()

                real.d = image
                inst_label.d = instance_id
                id_label.d = object_id

                # create fake
                fake.forward()

                # update discriminator
                d_solver.zero_grad()
                d_loss.forward()
                d_loss.backward(clear_buffer=True)

                if self.comm.n_procs > 1:
                    params = [
                        x.grad for x in d_solver.get_parameters().values()]
                    self.comm.all_reduce(params, division=False, inplace=False)
                d_solver.update()

                # update generator
                unlinked_fake.grad.zero()
                g_solver.zero_grad()
                g_loss.forward()
                g_loss.backward(clear_buffer=True)

                # backward generator
                fake.backward(grad=None, clear_buffer=True)

                if self.comm.n_procs > 1:
                    params = [
                        x.grad for x in g_solver.get_parameters().values()]
                    self.comm.all_reduce(params, division=False, inplace=False)
                g_solver.update()

                # report iteration progress
                reporter()

            # report epoch progress
            show_images = {"InputImage": label2color(id_label.data.get_data("r")).astype(np.uint8),
                           # "InputBoundary": bm.data.get_data("r").transpose((0, 2, 3, 1)),
                           "GeneratedImage": fake.data.get_data("r").transpose((0, 2, 3, 1)),
                           "RealImagse": real.data.get_data("r").transpose((0, 2, 3, 1))}
            reporter.epoch_end(show_images, epoch)

            if (epoch % 10) == 0 and self.comm.rank == 0:
                nn.save_parameters(os.path.join(
                    self.save_path, 'param_{:03d}.h5'.format(epoch)))

        if self.comm.rank == 0:
            nn.save_parameters(os.path.join(self.save_path, 'param_final.h5'))
