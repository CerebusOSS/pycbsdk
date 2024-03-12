from abc import abstractmethod
from ctypes import *
import struct
import numpy as np
import numpy.typing
from .. import config
from .common import (
    CBPacketType,
    CBSpecialChan,
)


# https://wumb0.in/a-better-way-to-work-with-raw-data-types-in-python.html


class CBPacketAbstract(Structure):
    _pack_ = 1

    def __new__(cls, buffer=None):
        if buffer:
            return cls.from_buffer_copy(buffer)
        else:
            return super().__new__(cls)

    def __init__(self, buffer=None):
        super().__init__()
        if not buffer:
            self.header.time = (
                0  # Will get updated to current proctime before being sent to device.
            )
            self.header.chid = self.default_chid
            self.header.type = self.default_type
            self.header.dlen = (sizeof(self.__class__) - sizeof(self.header)) // 4

    @property
    @abstractmethod
    def default_type(self) -> CBPacketType:
        pass

    @property
    @abstractmethod
    def default_chid(self) -> int:
        pass


class CBPacketVarLen(CBPacketAbstract):
    def __init__(self, buffer=None):
        super().__init__(buffer=buffer)  # Handles case of buffer is None
        if buffer and len(buffer) > sizeof(self.__class__):
            array_bytes = buffer[sizeof(self.__class__) :]
            n_bytes = len(array_bytes)
            n_items = n_bytes // sizeof(self._array._type_)
            self._array = (self._array._type_ * n_items)()
            memmove(self._array, array_bytes, n_bytes)
            # We don't update dlen to match n_items because dlen was set directly by the buffer.

    def __str__(self):
        return super(CBPacketVarLen, self).__str__() + "+" + self._array.__str__()

    def __bytes__(self):
        # Need a custom __bytes__ representation to add on _array. Unfortunately, we
        # can't start with `bytes(self)` because it is infinitely recursive.
        # TODO: Potential for optimization -- Get bytes representation of main body more quickly.
        out_bytes = b""
        for f, t in self._fields_:
            if isinstance(getattr(self, f), (int, float)):
                out_bytes += struct.pack(t._type_, getattr(self, f))
            else:
                out_bytes += bytes(getattr(self, f))
        return out_bytes + bytes(self._array)

    @property
    @abstractmethod
    def max_elements(self) -> int:
        pass

    @property
    def _array_nbytes(self):
        # return len(self._array) * sizeof(self._array._type_)
        return sizeof(self._array)

    @property
    def _body_nbytes(self):
        return sizeof(self.__class__) - sizeof(self.header) + self._array_nbytes

    def _update_dlen(self):
        self.header.dlen = self._body_nbytes // 4


class CBPacketVarDataNDArray(CBPacketVarLen):
    @property
    def data(self) -> np.ndarray:
        return np.ctypeslib.as_array(self._array)

    @data.setter
    def data(self, indata: numpy.typing.ArrayLike):
        inarray = np.asarray(indata, dtype=self._array._type_)
        assert inarray.ndim == 1
        n_elems = len(inarray)
        assert n_elems <= self.max_elements
        self._array = (self._array._type_ * n_elems).from_buffer(inarray)
        self._update_dlen()


class CBPacketConfigFixed(Structure):
    _pack_ = 1

    def __new__(cls, buffer=None):
        if buffer:
            return cls.from_buffer_copy(buffer)
        else:
            return super().__new__(cls)

    def __init__(self, buffer=None):
        super().__init__()
        if not buffer:
            self.header.time = (
                0  # Will get updated to current proctime before being sent to device.
            )
            self.header.chid = CBSpecialChan.CONFIGURATION
            self.header.type = self.default_type
            self.header.dlen = (sizeof(self.__class__) - sizeof(self.header)) // 4

    @property
    @abstractmethod
    def default_type(self):
        pass
