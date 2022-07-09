from typing import Callable, Optional, Sequence, Tuple, Union

import jax.lax as lax
import jax.numpy as jnp
import jax.random
import numpy as np

from ..custom_types import Array
from ..module import Module, static_field


class Pool(Module):
    """General N-dimensional downsampling over a sliding window."""

    init: Union[int, float, Array]
    operation: Callable[[Array, Array], Array]
    num_spatial_dims: int = static_field()
    kernel_size: Union[int, Sequence[int]] = static_field()
    stride: Union[int, Sequence[int]] = static_field()
    padding: Union[int, Sequence[int], Sequence[Tuple[int, int]]] = static_field()

    def __init__(
        self,
        init: Union[int, float, Array],
        operation: Callable[[Array, Array], Array],
        num_spatial_dims: int,
        kernel_size: Union[int, Sequence[int]],
        stride: Union[int, Sequence[int]] = 1,
        padding: Union[int, Sequence[int], Sequence[Tuple[int, int]]] = 0,
        **kwargs,
    ):
        """**Arguments:**

        - `init`: The initial value for the reduction.
        - `operation`: The operation applied to the inputs of each window.
        - `num_spatial_dims`: The number of spatial dimensions.
        - `kernel_size`: The size of the convolutional kernel.
        - `stride`: The stride of the convolution.
        - `padding`: The amount of padding to apply before and after each
            spatial dimension.

        !!! info

            In order for `Pool` to be differentiable, `operation(init, x) == x` needs to
            be true for all finite `x`. For further details see
            [https://www.tensorflow.org/xla/operation_semantics#reducewindow](https://www.tensorflow.org/xla/operation_semantics#reducewindow)
            and [https://github.com/google/jax/issues/7718](https://github.com/google/jax/issues/7718).
        """
        super().__init__(**kwargs)

        self.operation = operation
        self.init = init
        self.num_spatial_dims = num_spatial_dims

        if isinstance(kernel_size, int):
            self.kernel_size = (kernel_size,) * num_spatial_dims
        elif isinstance(kernel_size, Sequence):
            self.kernel_size = kernel_size
        else:
            raise ValueError(
                "`kernel_size` must either be an int or tuple of length "
                f"{num_spatial_dims} containing ints."
            )

        if isinstance(stride, int):
            self.stride = (stride,) * num_spatial_dims
        elif isinstance(stride, Sequence):
            self.stride = stride
        else:
            raise ValueError(
                "`stride` must either be an int or tuple of length "
                f"{num_spatial_dims} containing ints."
            )

        if isinstance(padding, int):
            self.padding = tuple((padding, padding) for _ in range(num_spatial_dims))
        elif isinstance(padding, Sequence) and len(padding) == num_spatial_dims:
            if all(isinstance(element, Sequence) for element in padding):
                self.padding = padding
            else:
                self.padding = tuple((p, p) for p in padding)
        else:
            raise ValueError(
                "`padding` must either be an int or tuple of length "
                f"{num_spatial_dims} containing ints or tuples of length 2."
            )

    def __call__(
        self, x: Array, *, key: Optional["jax.random.PRNGKey"] = None
    ) -> Array:
        """**Arguments:**

        - `x`: The input. Should be a JAX array of shape `(channels, dim_1, ..., dim_N)`, where
            `N = num_spatial_dims`.
        - `key`: Ignored; provided for compatibility with the rest of the Equinox API.
            (Keyword only argument.)

        **Returns:**

        A JAX array of shape `(channels, new_dim_1, ..., new_dim_N)`.
        """
        assert len(x.shape) == self.num_spatial_dims + 1, (
            f"Input should have {self.num_spatial_dims} spatial dimensions, "
            f"but input has shape {x.shape}"
        )

        x = jnp.moveaxis(x, 0, -1)
        x = jnp.expand_dims(x, axis=0)
        x = lax.reduce_window(
            x,
            self.init,
            self.operation,
            (1,) + self.kernel_size + (1,),
            (1,) + self.stride + (1,),
            ((0, 0),) + self.padding + ((0, 0),),
        )

        x = jnp.squeeze(x, axis=0)
        x = jnp.moveaxis(x, -1, 0)
        return x


class AvgPool1D(Pool):
    """One-dimensional downsample using an average over a sliding window."""

    def __init__(
        self,
        kernel_size,
        stride=None,
        padding=0,
        **kwargs,
    ):
        """**Arguments:**

        - `kernel_size`: The size of the convolutional kernel.
        - `stride`: The stride of the convolution.
        - `padding`: The amount of padding to apply before and after each
            spatial dimension.
        """

        super().__init__(
            init=0,
            operation=lax.add,
            num_spatial_dims=1,
            kernel_size=kernel_size,
            stride=stride,
            padding=padding,
            **kwargs,
        )

    def __call__(
        self, x: Array, *, key: Optional["jax.random.PRNGKey"] = None
    ) -> Array:
        """**Arguments:**

        - `x`: The input. Should be a JAX array of shape `(channels, dim)`.
        - `key`: Ignored; provided for compatibility with the rest of the Equinox API.
            (Keyword only argument.)

        **Returns:**

        A JAX array of shape `(channels, new_dim)`.
        """

        return super().__call__(x) / np.prod(self.kernel_size)


class MaxPool1D(Pool):
    """One-dimensional downsample using the maximum over a sliding window."""

    def __init__(
        self,
        kernel_size,
        stride=None,
        padding=0,
        **kwargs,
    ):
        """**Arguments:**

        - `kernel_size`: The size of the convolutional kernel.
        - `stride`: The stride of the convolution.
        - `padding`: The amount of padding to apply before and after each
            spatial dimension.
        """

        super().__init__(
            init=-jnp.inf,
            operation=lax.max,
            num_spatial_dims=1,
            kernel_size=kernel_size,
            stride=stride,
            padding=padding,
            **kwargs,
        )

    # Redefined to get them in the right order in docs
    def __call__(
        self, x: Array, *, key: Optional["jax.random.PRNGKey"] = None
    ) -> Array:
        """**Arguments:**

        - `x`: The input. Should be a JAX array of shape `(channels, dim)`.
        - `key`: Ignored; provided for compatibility with the rest of the Equinox API.
            (Keyword only argument.)

        **Returns:**

        A JAX array of shape `(channels, new_dim)`.
        """

        return super().__call__(x)


class AvgPool2D(Pool):
    """Two-dimensional downsample using an average over a sliding window."""

    def __init__(
        self,
        kernel_size,
        stride=None,
        padding=0,
        **kwargs,
    ):
        """**Arguments:**

        - `kernel_size`: The size of the convolutional kernel.
        - `stride`: The stride of the convolution.
        - `padding`: The amount of padding to apply before and after each
            spatial dimension.
        """

        super().__init__(
            init=0,
            operation=lax.add,
            num_spatial_dims=2,
            kernel_size=kernel_size,
            stride=stride,
            padding=padding,
            **kwargs,
        )

    def __call__(
        self, x: Array, *, key: Optional["jax.random.PRNGKey"] = None
    ) -> Array:
        """**Arguments:**

        - `x`: The input. Should be a JAX array of shape `(channels, dim_1, dim_2)`.
        - `key`: Ignored; provided for compatibility with the rest of the Equinox API.
            (Keyword only argument.)

        **Returns:**

        A JAX array of shape `(channels, new_dim_1, new_dim_2)`.
        """

        return super().__call__(x) / np.prod(self.kernel_size)


class MaxPool2D(Pool):
    """Two-dimensional downsample using the maximum over a sliding window."""

    def __init__(
        self,
        kernel_size,
        stride=None,
        padding=0,
        **kwargs,
    ):
        """**Arguments:**

        - `kernel_size`: The size of the convolutional kernel.
        - `stride`: The stride of the convolution.
        - `padding`: The amount of padding to apply before and after each
            spatial dimension.
        """

        super().__init__(
            init=-jnp.inf,
            operation=lax.max,
            num_spatial_dims=2,
            kernel_size=kernel_size,
            stride=stride,
            padding=padding,
            **kwargs,
        )

    # Redefined to get them in the right order in docs
    def __call__(
        self, x: Array, *, key: Optional["jax.random.PRNGKey"] = None
    ) -> Array:
        """**Arguments:**

        - `x`: The input. Should be a JAX array of shape `(channels, dim_1, dim_2)`.
        - `key`: Ignored; provided for compatibility with the rest of the Equinox API.
            (Keyword only argument.)

        **Returns:**

        A JAX array of shape `(channels, new_dim_1, new_dim_2)`.
        """

        return super().__call__(x)


class AvgPool3D(Pool):
    """Three-dimensional downsample using an average over a sliding window."""

    def __init__(
        self,
        kernel_size,
        stride=None,
        padding=0,
        **kwargs,
    ):
        """**Arguments:**

        - `kernel_size`: The size of the convolutional kernel.
        - `stride`: The stride of the convolution.
        - `padding`: The amount of padding to apply before and after each
            spatial dimension.
        """

        super().__init__(
            init=0,
            operation=lax.add,
            num_spatial_dims=3,
            kernel_size=kernel_size,
            stride=stride,
            padding=padding,
            **kwargs,
        )

    def __call__(
        self, x: Array, *, key: Optional["jax.random.PRNGKey"] = None
    ) -> Array:
        """**Arguments:**

        - `x`: The input. Should be a JAX array of shape
            `(channels, dim_1, dim_2, dim_3)`.
        - `key`: Ignored; provided for compatibility with the rest of the Equinox API.
            (Keyword only argument.)

        **Returns:**

        A JAX array of shape `(channels, new_dim_1, new_dim_2, new_dim_3)`.
        """

        return super().__call__(x) / np.prod(self.kernel_size)


class MaxPool3D(Pool):
    """Three-dimensional downsample using the maximum over a sliding window."""

    def __init__(
        self,
        kernel_size,
        stride=None,
        padding=0,
        **kwargs,
    ):
        """**Arguments:**

        - `kernel_size`: The size of the convolutional kernel.
        - `stride`: The stride of the convolution.
        - `padding`: The amount of padding to apply before and after each
            spatial dimension.
        """

        super().__init__(
            init=-jnp.inf,
            operation=lax.max,
            num_spatial_dims=3,
            kernel_size=kernel_size,
            stride=stride,
            padding=padding,
            **kwargs,
        )

    def __call__(
        self, x: Array, *, key: Optional["jax.random.PRNGKey"] = None
    ) -> Array:
        """**Arguments:**

        - `x`: The input. Should be a JAX array of shape
            `(channels, dim_1, dim_2, dim_3)`.
        - `key`: Ignored; provided for compatibility with the rest of the Equinox API.
            (Keyword only argument.)

        **Returns:**

        A JAX array of shape `(channels, new_dim_1, new_dim_2, new_dim_3)`.
        """

        return super().__call__(x)


def adaptive_avg_pool1d(x: Array, target_size: int):
    """See `equinox.nn.pool.AdaptiveAvgPool1D` for details on the arguments"""
    if x.ndim != 1:
        raise ValueError(f"1D input expected, received input with {x.ndim} dimensions.")

    channels = jnp.size(x)
    if channels < target_size:
        raise ValueError(
            "`target_size` cannot be larger than the input channels."
            f"Expected atleast {target_size} but received {channels}."
        )
    num_head_arrays = channels % target_size
    if num_head_arrays != 0:
        head_end_index = num_head_arrays * (channels // target_size + 1)
        head_mean = jax.vmap(jnp.mean)(x[:head_end_index].reshape(num_head_arrays, -1))
        tail_mean = jax.vmap(jnp.mean)(
            x[head_end_index:].reshape(-1, channels // target_size)
        )
        mean = jnp.concatenate([head_mean, tail_mean])
    else:
        mean = jax.vmap(jnp.mean)(
            jax.vmap(jnp.mean)(x.reshape(-1, channels // target_size))
        )
    return mean


class AdaptiveAvgPool1D(Module):
    """Adaptive 1D downsampling for a target shape."""

    target_size: int = static_field()

    def __init__(self, target_size: int):
        """**Arguments:**

        - `target_size`: The target output size.
        """

        self.target_size = target_size

    def __call__(
        self, x: Array, *, key: Optional["jax.random.PRNGKey"] = None
    ) -> Array:
        """**Arguments:**

        - `x`: The input. Should be a JAX array of shape `(channels)`.
        - `key`: Ignored; provided for compatibility with the rest of the Equinox API.
            (Keyword only argument.)

        **Returns:**

        A JAX array of shape `(target_size)`.
        """
        mean = adaptive_avg_pool1d(x, self.target_size)
        return mean


class AdaptiveAvgPool2D(Module):
    """Adaptive 2D downsampling for a target shape."""

    target_size: Union[int, Sequence[int]] = static_field()

    def __init__(self, target_size: Union[int, Sequence[int]]):
        """**Arguments:**

        - `target_size`: The target output size.
        """
        if isinstance(target_size, int):
            target_size = (target_size, target_size)
        self.target_size = target_size

    def __call__(
        self, x: Array, *, key: Optional["jax.random.PRNGKey"] = None
    ) -> Array:
        """**Arguments:**

        - `x`: The input. Should be a JAX array of shape `(channel, dims)`.
        - `key`: Ignored; provided for compatibility with the rest of the Equinox API.
            (Keyword only argument.)

        **Returns:**

        A JAX array of shape `(target_size)`.
        """
        if x.ndim != 2:
            raise ValueError(
                f"2D input expected, received input with {x.ndim} dimensions."
            )

        channels, dims = x.shape
        if channels < self.target_size[0] or dims < self.target_size[1]:
            raise ValueError(
                "`target_size` cannot be larger than the input channels."
                f"Expected atleast {self.target_size} but received {channels}x{dims}."
            )
        target_channels, target_dims = self.target_size

        x = jax.vmap(adaptive_avg_pool1d, in_axes=(0, None))(x, target_dims)
        x = jax.vmap(adaptive_avg_pool1d, in_axes=(0, None))(
            jnp.transpose(x), target_channels
        )
        return jnp.transpose(x)
