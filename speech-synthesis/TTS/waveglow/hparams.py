# Copyright (c) 2017 Sony Corporation. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from utils.hparams import HParams

hparams = HParams(

    # dataset parameters
    data_dir="./data/LJSpeech-1.1/",               # directory to the data
    save_data_dir="./data/LJSpeech-1.1/waveglow",  # directory to store audios
    out_variables=["audio"],            # which variables will be used

    # spectrogram parameters
    sr=22050,                           # sampling rate used to read audios
    n_fft=1024,                         # length of the windowed signal after padding with zeros.
    n_mels=80,                          # number of mel filters
    mel_fmin=0.0,                       # minimum mel bank
    mel_fmax=8000.0,                    # maximum mel bank
    hop_length=256,                     # number of audio samples between adjacent STFT columns
    win_length=1024,                    # window length

    # flow parameters
    n_flows=12,                         # number of flow nets
    n_groups=8,                         # number of Number of samples in a group processed by the steps of flow
    n_early_every=4,                    # Determines how often (i.e., after how many coupling layers)
                                        # a number of channels are output to the loss function
    n_early_size=2,                     # Number of channels output to the loss function
    sigma=1.0,                          # Standard deviation used for sampling from Gaussian
    segment_length=8000,                # Segment length (audio samples) processed per iteration
    wn_n_layers=8,                      # Number of layers in WN
    wn_kernel_size=3,                   # Kernel size for dialted convolution in the affine coupling layer (WN)
    wn_n_channels=256,                  # Number of channels in WN
    seed=123456,                        # random seed

    # optimization parameters
    batch_size=4,                       # batch size
    epoch=1001,                         # number of epochs
    print_frequency=20,                 # number of iterations before printing to log file
    epochs_per_checkpoint=50,           # number of epochs for each checkpoint
    output_path="./log/waveglow/",      # directory to save results

    weight_decay=0.0,                   # weight decay
    max_norm=3.4028234663852886e+38,    # maximum norm used in clip_grad_by_norm
    alpha=1e-4,                         # learning rate
    anneal_factor=0.1,                  # factor by which to anneal the learning rate
    anneal_steps=()                     # epoch at which to anneal the learning rate
)