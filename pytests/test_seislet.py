import pytest
import numpy as np
from numpy.testing import assert_array_almost_equal

from pylops.utils import dottest
from pylops.basicoperators import FunctionOperator
from pylops.signalprocessing.Seislet import _predict_trace, _predict
from pylops.signalprocessing import Seislet

par1 = {'nx': 16, 'nt': 30, 'dx': 10, 'dt': 0.004, 'level': None,
        'dtype': 'float32'}
par2 = {'nx': 16, 'nt': 30, 'dx': 10, 'dt': 0.004, 'level': 2,
        'dtype': 'float32'}

np.random.seed(10)


@pytest.mark.parametrize("par", [(par1)])
def test_predict_trace(par):
    """Dot-test for _predict_trace operator
    """
    t = np.arange(par['nt']) * par['dt']
    for slope in [-0.2, 0., 0.3]:
        Fop = FunctionOperator(
            lambda x: _predict_trace(x, t, par['dt'], par['dx'], slope),
            lambda x: _predict_trace(x, t, par['dt'], par['dx'], slope, adj=True),
            par['nt'], par['nt'])
        dottest(Fop, par['nt'], par['nt'])



@pytest.mark.parametrize("par", [(par1)])
def test_predict(par):
    """Dot-test for _predict operator
    """
    def _predict_reshape(traces, nt, nx, dt, dx, slopes, repeat=0,
                         backward=False, adj=False):
        return _predict(traces.reshape(nt, nx), dt, dx, slopes, repeat=repeat,
                        backward=backward, adj=adj)

    for repeat in (0, 1, 2):
        slope = \
            np.random.normal(0, .1, (par['nt'], 2 ** (repeat + 1) * par['nx']))
        for backward in (False, True):
            Fop = FunctionOperator(
                lambda x: _predict_reshape(x, par['nt'], par['nx'],
                                           par['dt'], par['dx'],
                                           slope, backward=backward),
                lambda x: _predict_reshape(x, par['nt'], par['nx'],
                                           par['dt'], par['dx'],
                                           slope, backward=backward, adj=True),
                par['nt']*par['nx'], par['nt']*par['nx'])
            dottest(Fop, par['nt']*par['nx'], par['nt']*par['nx'])


@pytest.mark.parametrize("par", [(par1), (par2)])
def test_Seislet(par):
    """Dot-test and forward-inverse for Seislet
    """
    slope = np.random.normal(0, .1, (par['nt'], par['nx']))

    Sop = Seislet(slope, sampling=(par['dt'], par['dx']), level=par['level'],
                  dtype=par['dtype'])
    dottest(Sop, par['nt']*par['nx'], par['nt']*par['nx'])

    x = np.random.normal(0, .1, par['nt'] * par['nx'])
    y = Sop * x
    xinv = Sop.inverse(y)

    assert_array_almost_equal(x, xinv)