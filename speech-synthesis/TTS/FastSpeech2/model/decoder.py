import nnabla.functions as F

from utils.ops import masked_fill

from .module import Module
from .transformer.layer import FFTBlock
from .transformer.ops import get_positional_encoding


class Decoder(Module):
    r"""Decoder module.

    Args:
        hp (Hparams): Hyper-parameters.
    """

    def __init__(self, hp):
        self.hp = hp
        self.pos_enc = get_positional_encoding(
            hp.max_len_mel, hp.decoder_hidden
        )
        for i in range(hp.decoder_layer):
            setattr(
                self, f"fft_block_{i}",
                FFTBlock(
                    n_head=hp.decoder_head,
                    n_hidden=hp.decoder_hidden,
                    conv_filter_size=hp.conv_filter_size,
                    conv_kernel_size=hp.conv_kernel_size,
                    dropout=hp.decoder_dropout
                )
            )

    def call(self, x, mask=None):
        r"""Compute mel-spectrogram from emebdding.

        Args:
            x (nn.Variable): Embedding variable of shape (B, max_len, dim).
            mask (nn.Variable): Mask vairable of shape (B, max_len, 1).
                Defaults to None.

        Returns:
            nn.Variable: Output variable of shape (B, max_len, dim).
        """
        hp = self.hp
        x = x + F.tile(self.pos_enc, (hp.batch_size, 1, 1))

        if mask is not None:
            mask = F.transpose(mask, (0, 2, 1))

        for i in range(hp.decoder_layer):
            x = getattr(self, f"fft_block_{i}")(x, mask)

        # remove masked output
        if mask is not None:
            x = masked_fill(x, F.transpose(mask, (0, 2, 1)))

        return x
