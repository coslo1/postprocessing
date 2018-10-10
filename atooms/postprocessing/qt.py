# This file is part of atooms
# Copyright 2010-2018, Daniele Coslovich

"""Time-dependent overlap."""

import numpy

from .helpers import logx_grid
from .correlation import Correlation, gcf_offset
from .helpers import adjust_skip, setup_t_grid

__all__ = ['CollectiveOverlap', 'SelfOverlap']


def pairs_numpy(f, x, y, L):
    """
    Apply function f to all pairs in x[i] and y[j] and return a numpy
    array of f values.
    """
    fxy = numpy.ndarray((len(y), len(x)))
    for i in range(fxy.shape[0]):
        fxy[i, :] = f(x[:], y[i], L)
    return fxy

def square_displacement(x, y, L=None):
    """Return array of square distances (no pbc)."""
    return numpy.sum((x-y)**2, axis=1)

def collective_overlap(r0, r1, side, a_square):
    rij = pairs_numpy(square_displacement, r0, r1, side)
    return (rij.flatten() < a_square).sum()

def self_overlap(r0, r1, side, a_square):
    rij = square_displacement(r0, r1)
    return rij.flatten() < a_square


class CollectiveOverlap(Correlation):

    """Time-dependent collective overlap."""

    # TODO: why dont we use PBCed distance here?!

    def __init__(self, trajectory, tgrid=None, tsamples=60, a=0.3,
                 norigins=-1):
        Correlation.__init__(self, trajectory, tgrid, 'Q(t)', 'qt',
                             'collective overlap', 'pos')
        self.a_square = a**2
        self.skip = adjust_skip(self.trajectory, norigins)
        if tgrid is None:
            self.grid = logx_grid(0.0, trajectory.total_time * 0.75, tsamples)
        self._discrete_tgrid = setup_t_grid(trajectory, self.grid)

    def _compute(self):
        side = self.trajectory.read(0).cell.side
        def f(x, y):
            return collective_overlap(x, y, side, self.a_square).sum() / float(x.shape[0])
        self.grid, self.value = gcf_offset(f, self._discrete_tgrid,
                                           self.skip, self.trajectory.steps, self._pos)
        self.grid = [ti * self.trajectory.timestep for ti in self.grid]


class SelfOverlap(Correlation):

    """Time-dependent self overlap."""

    def __init__(self, trajectory, tgrid=None, norigins=-1, a=0.3,
                 tsamples=60):
        Correlation.__init__(self, trajectory, tgrid, 'Q_s(t)', 'qst',
                             'self overlap', 'pos-unf')
        if not self._need_update:
            return
        if tgrid is None:
            self.grid = logx_grid(0.0, trajectory.total_time * 0.75, tsamples)
        self._discrete_tgrid = setup_t_grid(trajectory, self.grid)
        self.skip = adjust_skip(self.trajectory, norigins)
        self.a_square = a**2

    def _compute(self):
        side = self.trajectory.read(0).cell.side
        def f(x, y):
            return self_overlap(x, y, side, self.a_square).sum() / float(x.shape[0])
        self.grid, self.value = gcf_offset(f, self._discrete_tgrid,
                                           self.skip, self.trajectory.steps, self._pos_unf)
        self.grid = [ti * self.trajectory.timestep for ti in self.grid]

    def analyze(self):
        try:
            from .helpers import feqc
            self.results['tau'] = feqc(self.grid, self.value, 1 / numpy.exp(1.0))[0]
        except:
            self.results['tau'] = None
