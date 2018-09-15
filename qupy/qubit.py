# -*- coding: utf-8 -*-
from __future__ import division
from __future__ import print_function
import numpy as np
import math
import sys
import qupy.operator
try:
    import cupy
except:
    pass


class Qubits:
    """
    Creating qubits.

    Args:
        size (:class:`int`):
            Number of qubits.
        dtype:
            Data type of the data array.
        gpu (:class:`int`):
            GPU machine number.

    Attributes:
        data (:class:`numpy.ndarray` or :class:`cupy.ndarray`):
            The state of qubits.
        size:
            Number of qubits.
        dtype:
            Data type of the data array.
    """

    def __init__(self, size, dtype=np.complex128, gpu=-1):
        if gpu >= 0:
            self.xp = cupy
            self.xp.cuda.Device(gpu).use()
        else:
            self.xp = np

        self.size = size
        self.dtype = dtype

        self.data = self.xp.zeros([2] * self.size, dtype=dtype)
        self.data[tuple([0] * self.size)] = 1

    def set_state(self, state):
        """set_state(self, state)

        Set state.

        Args:
            state (:class:`str` or :class:`list` or :class:`numpy.ndarray` or :class:`cupy.ndarray`):
                If you set state as :class:`str`, you can set state \state>
                (e.g. state='0110' -> \0110>.)
                otherwise, qubit state is set that you entered as state.
        """
        if isinstance(state, str):
            assert len(state) == self.data.ndim, 'There were {} qubits prepared, but you specified {} qubits'.format(
                self.data.ndim, len(state))
            self.data = self.xp.zeros_like(self.data)
            self.data[tuple([int(i) for i in state])] = 1
        else:
            self.data = self.xp.asarray(state, dtype=self.dtype)
            if self.data.ndim == 1:
                self.data = self.data.reshape([2] * self.size)

    def get_state(self, flatten=True):
        """get_state(self, flatten=True)

        Get state.

        Args:
            flatten (:class:`bool`):
                If you set flatten=False, you can get data format used in QuPy.
                otherwise, you get state reformated to 1D-array.
        """
        if flatten:
            return self.data.flatten()
        return self.data

    def gate(self, operator, target, control=None, control_0=None):
        """gate(self, operator, target, control=None, control_0=None)

        Gate method.

        Args:
            operator (:class:`numpy.ndarray` or :class:`cupy.ndarray`):
                Unitary operator
            target (None or :class:`int` or :class:`tuple` of :class:`int`):
                Operated qubits
            control (None or :class:`int` or :class:`tuple` of :class:`int`):
                Operate target qubits where all control qubits are 1
            control_0 (None or :class:`int` or :class:`tuple` of :class:`int`):
                Operate target qubits where all control qubits are 0
        """
        xp = self.xp

        if np.issubdtype(type(target), np.integer):
            target = (target,)
        if np.issubdtype(type(control), np.integer):
            control = (control,)
        if np.issubdtype(type(control_0), np.integer):
            control_0 = (control_0,)

        operator = xp.asarray(operator, dtype=self.dtype)
        if operator.shape[0] != 2:
            operator = operator.reshape([2] * int(math.log2(operator.size)))

        assert operator.ndim == len(target) * 2, 'You must set operator.size==exp(len(target)*2)'

        c_slice = [slice(None)] * self.size
        if control is not None:
            for _c in control:
                c_slice[_c] = slice(1, 2)
        if control_0 is not None:
            for _c in control_0:
                c_slice[_c] = slice(0, 1)
        c_slice = tuple(c_slice)

        c_index = list(range(self.size))
        t_index = list(range(self.size))
        for i, _t in enumerate(target):
            t_index[_t] = self.size + i
        o_index = list(range(self.size, self.size + len(target))) + list(target)

        # Use following code when numpy bug is removed and cupy can use this einsum format.
        # self.data[c_slice] = xp.einsum(operator, o_index, self.data[c_slice], c_index, t_index)

        # Alternative code
        character = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
        o_index = ''.join([character[i] for i in o_index])
        c_index = ''.join([character[i] for i in c_index])
        t_index = ''.join([character[i] for i in t_index])
        subscripts = '{},{}->{}'.format(o_index, c_index, t_index)
        self.data[c_slice] = xp.einsum(subscripts, operator, self.data[c_slice])

    def project(self, target):
        """projection(self, target)

        Projection method.

        Args:
            target (None or :class:`int` or :class:`tuple` of :class:`int`):
                projected qubits

        Returns:
            :class:`int`: O or 1.
        """
        xp = self.xp

        self.data = xp.asarray(self.data, dtype=self.dtype)
        if self.data.ndim == 1:
            self.data = self.data.reshape([2] * self.size)

        data = xp.split(self.data, [1], axis=target)
        p = [self._to_scalar(xp.sum(data[i] * xp.conj(data[i])).real) for i in (0, 1)]
        obs = self._to_scalar(xp.random.choice([0, 1], p=p))

        if obs == 0:
            self.data = xp.concatenate((data[obs] / math.sqrt(p[obs]), xp.zeros_like(data[obs])), target)
        else:
            self.data = xp.concatenate((xp.zeros_like(data[obs]), data[obs] / math.sqrt(p[obs])), target)
        return obs

    def expect(self, operator):
        """expect(self, operator)

        Method to get expected value.

        Args:
            operator (:class:`dict` or :class:`numpy.ndarray` or :class:`cupy.ndarray`):
                Physical quantity operator.

        Returns:
            :class:`float`: Expected value.
        """
        xp = self.xp

        if isinstance(operator, dict):
            tmp = xp.zeros_like(self.data)
            org_data = self.data

            for key, value in operator.items():
                self.data = xp.copy(org_data)
                assert len(key) == self.size, \
                    'Length of each key must be {} but len({}) is {}.'.format(self.size, key, len(key))

                for i, op in enumerate(key):
                    if op in 'XYZ':
                        self.gate(getattr(qupy.operator, op), target=i)
                    else:
                        assert op == 'I', 'Keys of input must not include {}.'.format(op)

                tmp += self.data * value

            self.data = org_data

            return np.einsum('i,i', np.conj(tmp.flatten()), self.data.flatten())

        else:
            assert operator.size == self.data.size ** 2, \
                'operator.size must be {}. Actual: {}'.format(self.data.size ** 2, operator.size)
            operator = xp.asarray(operator, dtype=self.dtype)
            if operator.shape[0] != self.data.size:
                operator = operator.reshape((self.data.size, self.data.size))

            return np.einsum('i,ij,j', np.conj(self.data.flatten()), operator, self.data.flatten())

    def _to_scalar(self, x):
        if self.xp != np:
            if isinstance(x, cupy.ndarray):
                x = cupy.asnumpy(x)
        if isinstance(x, np.ndarray):
            x = np.asscalar(x)
        return x

    def projection(self, target):
        sys.stderr.write('`qupy.projection` method is abolished soon. Please use `qupy.project`.\n')
        return self.project(target)
