import multiprocessing as mp
import numpy as np

from scipy.sparse.linalg.interface import _get_dtype
from scipy.sparse.linalg.interface import LinearOperator as spLinearOperator
from pylops import LinearOperator
from pylops.basicoperators import MatrixMult
from pylops.utils.backend import get_array_module


def _matvec_rmatvec_map(op, x):
    """matvec/rmatvec for multiprocessing
    """
    return op(x).squeeze()


class BlockDiag(LinearOperator):
    r"""Block-diagonal operator.

    Create a block-diagonal operator from N linear operators.

    Parameters
    ----------
    ops : :obj:`list`
        Linear operators to be stacked. Alternatively,
        :obj:`numpy.ndarray` or :obj:`scipy.sparse` matrices can be passed
        in place of one or more operators.
    nproc : :obj:`int`, optional
        Number of processes used to evaluate the N operators in parallel using
        ``multiprocessing``. If ``nproc=1``, work in serial mode.
    dtype : :obj:`str`, optional
        Type of elements in input array.

    Attributes
    ----------
    shape : :obj:`tuple`
        Operator shape
    explicit : :obj:`bool`
        Operator contains a matrix that can be solved explicitly (``True``) or
        not (``False``)

    Notes
    -----
    A block-diagonal operator composed of N linear operators is created such
    as its application in forward mode leads to

    .. math::
        \begin{bmatrix}
            \mathbf{L_1}  & \mathbf{0}   &  ... &  \mathbf{0}  \\
            \mathbf{0}    & \mathbf{L_2} &  ... &  \mathbf{0}  \\
            ...           & ...          &  ... &  ...         \\
            \mathbf{0}    & \mathbf{0}   &  ... &  \mathbf{L_N}
        \end{bmatrix}
        \begin{bmatrix}
            \mathbf{x}_{1}  \\
            \mathbf{x}_{2}  \\
            ...     \\
            \mathbf{x}_{N}
        \end{bmatrix} =
        \begin{bmatrix}
            \mathbf{L_1} \mathbf{x}_{1}  \\
            \mathbf{L_2} \mathbf{x}_{2}  \\
            ...     \\
            \mathbf{L_N} \mathbf{x}_{N}
        \end{bmatrix}

    while its application in adjoint mode leads to

    .. math::
        \begin{bmatrix}
            \mathbf{L_1}^H  \quad \mathbf{0}    \quad ... \quad  \mathbf{0}  \\
            \mathbf{0}    \quad \mathbf{L_2}^H  \quad ... \quad  \mathbf{0}  \\
            ...           \quad ...             \quad ... \quad  ...         \\
            \mathbf{0}    \quad \mathbf{0}      \quad ... \quad  \mathbf{L_N}^H
        \end{bmatrix}
        \begin{bmatrix}
            \mathbf{y}_{1}  \\
            \mathbf{y}_{2}  \\
            ...     \\
            \mathbf{y}_{N}
        \end{bmatrix} =
        \begin{bmatrix}
            \mathbf{L_1}^H \mathbf{y}_{1}  \\
            \mathbf{L_2}^H \mathbf{y}_{2}  \\
            ...     \\
            \mathbf{L_N}^H \mathbf{y}_{N}
        \end{bmatrix}

    """
    def __init__(self, ops, nproc=1, dtype=None):
        self.ops = ops
        mops = np.zeros(len(ops), dtype=np.int)
        nops = np.zeros(len(ops), dtype=np.int)
        for iop, oper in enumerate(ops):
            if not isinstance(oper, (LinearOperator, spLinearOperator)):
                self.ops[iop] = MatrixMult(oper, dtype=oper.dtype)
            nops[iop] = self.ops[iop].shape[0]
            mops[iop] = self.ops[iop].shape[1]
        self.nops = int(nops.sum())
        self.mops = int(mops.sum())
        self.nnops = np.insert(np.cumsum(nops), 0, 0)
        self.mmops = np.insert(np.cumsum(mops), 0, 0)
        # create pool for multiprocessing
        self._nproc = nproc
        self.pool = None
        if self.nproc > 1:
            self.pool = mp.Pool(processes=nproc)
        self.shape = (self.nops, self.mops)
        if dtype is None:
            self.dtype = _get_dtype(ops)
        else:
            self.dtype = np.dtype(dtype)
        self.explicit = False

    @property
    def nproc(self):
        return self._nproc

    @nproc.setter
    def nproc(self, nprocnew):
        if self._nproc > 1:
            self.pool.close()
        if nprocnew > 1:
            self.pool = mp.Pool(processes=nprocnew)
        self._nproc = nprocnew

    def _matvec_serial(self, x):
        ncp = get_array_module(x)
        y = ncp.zeros(self.nops, dtype=self.dtype)
        for iop, oper in enumerate(self.ops):
            y[self.nnops[iop]:self.nnops[iop + 1]] = \
                oper.matvec(x[self.mmops[iop]:self.mmops[iop + 1]]).squeeze()
        return y

    def _rmatvec_serial(self, x):
        ncp = get_array_module(x)
        y = ncp.zeros(self.mops, dtype=self.dtype)
        for iop, oper in enumerate(self.ops):
            y[self.mmops[iop]:self.mmops[iop + 1]] = \
                oper.rmatvec(x[self.nnops[iop]:self.nnops[iop + 1]]).squeeze()
        return y

    def _matvec_multiproc(self, x):
        ys = self.pool.starmap(_matvec_rmatvec_map,
                               [(oper._matvec, x[self.mmops[iop]:self.mmops[iop + 1]])
                                for iop, oper in enumerate(self.ops)])
        y = np.hstack(ys)
        return y

    def _rmatvec_multiproc(self, x):
        ys = self.pool.starmap(_matvec_rmatvec_map,
                               [(oper._rmatvec, x[self.nnops[iop]:self.nnops[iop + 1]])
                                for iop, oper in enumerate(self.ops)])
        y = np.hstack(ys)
        return y

    def _matvec(self, x):
        if self.nproc == 1:
            y = self._matvec_serial(x)
        else:
            y = self._matvec_multiproc(x)
        return y

    def _rmatvec(self, x):
        if self.nproc == 1:
            y = self._rmatvec_serial(x)
        else:
            y = self._rmatvec_multiproc(x)
        return y
