# This file is part of atooms
# Copyright 2010-2018, Daniele Coslovich

"""Intermediate scattering function."""

import sys
from collections import defaultdict

import numpy
from atooms.trajectory.utils import check_block_size

from .helpers import logx_grid, setup_t_grid
from .correlation import Correlation
from .fourierspace import FourierSpaceCorrelation, expo_sphere
from .progress import progress

__all__ = ['SelfIntermediateScattering', 'IntermediateScattering']


def _write_tau(out, db):
    # Custom writing of relaxation times
    out.write('# title: relaxation times tau(k) as a function of k\n')
    out.write('# columns: k, tau(k)\n')
    out.write('# note: tau is the time at which the correlation function has decayed to 1/e\n')
    for k, tau in db['relaxation times tau'].items():
        if tau is None:
            out.write('%g\n' % k)
        else:
            out.write('%g %g\n' % (k, tau))

def _extract_tau(k, t, f):
    from .helpers import feqc
    tau = {}
    for i, k in enumerate(k):
        try:
            tau[k] = feqc(t, f[i], 1 / numpy.exp(1.0))[0]
        except ValueError:
            tau[k] = None
    return tau


class SelfIntermediateScattering(FourierSpaceCorrelation):
    """
    Self part of the intermediate scattering function.

    See the documentation of the `FourierSpaceCorrelation` base class
    for information on the instance variables.
    """

    symbol = 'fskt'
    short_name = 'F_s(k,t)'
    long_name = 'self intermediate scattering function'
    phasespace = 'pos-unf'

    #TODO: xyz files are 2 slower than hdf5 here
    def __init__(self, trajectory, kgrid=None, tgrid=None, nk=8, tsamples=60,
                 dk=0.1, kmin=1.0, kmax=10.0, ksamples=10, norigins=-1):
        FourierSpaceCorrelation.__init__(self, trajectory, [kgrid, tgrid], norigins,
                                         nk, dk, kmin, kmax, ksamples)
        # Setup time grid
        # Before setting up the time grid, we need to check periodicity over blocks
        check_block_size(self.trajectory.steps, self.trajectory.block_size)
        if tgrid is None:
            self.grid[1] = [0.0] + logx_grid(self.trajectory.timestep,
                                             self.trajectory.total_time * 0.75, tsamples)
        self._discrete_tgrid = setup_t_grid(self.trajectory, self.grid[1])

    def _compute(self):
        # Pick up a random, unique set of nk vectors out ot the avilable ones
        # without exceeding maximum number of vectors in shell nkmax
        # TODO: Can this be moved up the chain?
        self.k_sorted, self.k_selected = self._decimate_k()

        # Throw everything into a big numpy array
        # TODO: remove this redundancy
        self._pos = self._pos_unf
        pos = numpy.ndarray((len(self._pos), ) + self._pos[0].shape)
        for i in range(len(self._pos)):
            pos[i, :, :] = self._pos[i]

        # To optimize without wasting too much memory (we really have
        # troubles here) we group particles in blocks and tabulate the
        # exponentials over time this is more memory consuming but we
        # can optimize the inner loop.  even better we could change
        # order in the tabulated expo array to speed things up shape
        # is (Npart, Ndim)
        block = min(20, self._pos[0].shape[0])
        kmax = max(self.kvec.keys()) + self.dk
        acf = [defaultdict(float) for _ in self.k_sorted]
        cnt = [defaultdict(float) for _ in self.k_sorted]
        if self.trajectory.block_size > 1:
            skip = self.trajectory.block_size
        else:
            skip = self.skip

        origins = range(0, pos.shape[1], block)
        for j in progress(origins):
            x = expo_sphere(self.k0, kmax, pos[:, j:j + block, :])
            for kk, knorm in enumerate(self.k_sorted):
                for kkk in self.k_selected[kk]:
                    ik = self.kvec[knorm][kkk]
                    for off, i in self._discrete_tgrid:
                        for i0 in range(off, x.shape[0]-i, skip):
                            # Get the actual time difference. steps must be accessed efficiently (cached!)
                            dt = self.trajectory.steps[i0+i] - self.trajectory.steps[i0]
                            acf[kk][dt] += numpy.sum(x[i0+i, :, 0, ik[0]]*x[i0, :, 0, ik[0]].conjugate() *
                                                     x[i0+i, :, 1, ik[1]]*x[i0, :, 1, ik[1]].conjugate() *
                                                     x[i0+i, :, 2, ik[2]]*x[i0, :, 2, ik[2]].conjugate()).real
                            cnt[kk][dt] += x.shape[1]

        t_sorted = sorted(acf[0].keys())
        self.grid[0] = self.k_sorted
        self.grid[1] = [ti*self.trajectory.timestep for ti in t_sorted]
        self.value = [[acf[kk][ti] / cnt[kk][ti] for ti in t_sorted] for kk in range(len(self.grid[0]))]
        self.value = [[self.value[kk][i] / self.value[kk][0] for i in range(len(self.value[kk]))] for kk in range(len(self.grid[0]))]

    def analyze(self):
        self.analysis['relaxation times tau'] = _extract_tau(self.grid[0], self.grid[1], self.value)

    def write(self):
        Correlation.write(self)
        if self._output_file != '/dev/stdout':
            with open(self._output_file + '.tau', 'w') as out:
                _write_tau(out, self.analysis)


class IntermediateScattering(FourierSpaceCorrelation):
    """
    Coherent intermediate scattering function.

    See the documentation of the `FourierSpaceCorrelation` base class
    for information on the instance variables.
    """

    nbodies = 2
    symbol = 'fkt'
    short_name = 'F(k,t)'
    long_name = 'intermediate scattering function'
    phasespace = 'pos'

    def __init__(self, trajectory, kgrid=None, tgrid=None, nk=100, dk=0.1, tsamples=60,
                 kmin=1.0, kmax=10.0, ksamples=10, norigins=-1):
        FourierSpaceCorrelation.__init__(self, trajectory, [kgrid, tgrid], norigins,
                                         nk, dk, kmin, kmax, ksamples)
        # Setup time grid
        check_block_size(self.trajectory.steps, self.trajectory.block_size)
        if tgrid is None:
            self.grid[1] = logx_grid(0.0, self.trajectory.total_time * 0.75, tsamples)
        self._discrete_tgrid = setup_t_grid(self.trajectory, self.grid[1])

    def _tabulate_rho(self, k_sorted, k_selected):
        """
        Tabulate densities
        """
        nsteps = len(self._pos_0)
        kmax = max(self.kvec.keys()) + self.dk
        rho_0 = [defaultdict(complex) for it in range(nsteps)]
        rho_1 = [defaultdict(complex) for it in range(nsteps)]
        for it in range(nsteps):
            expo_0 = expo_sphere(self.k0, kmax, self._pos_0[it])
            # Optimize a bit here: if there is only one filter (alpha-alpha or total calculation)
            # expo_2 will be just a reference to expo_1
            if self._pos_1 is self._pos_0:
                expo_1 = expo_0
            else:
                expo_1 = expo_sphere(self.k0, kmax, self._pos_1[it])

            # Tabulate densities rho_0, rho_1
            for kk, knorm in enumerate(k_sorted):
                for i in k_selected[kk]:
                    ik = self.kvec[knorm][i]
                    rho_0[it][ik] = numpy.sum(expo_0[..., 0, ik[0]] * expo_0[..., 1, ik[1]] * expo_0[..., 2, ik[2]])
                    # Same optimization as above: only calculate rho_1 if needed
                    if self._pos_1 is not self._pos_0:
                        rho_1[it][ik] = numpy.sum(expo_1[..., 0, ik[0]] * expo_1[..., 1, ik[1]] * expo_1[..., 2, ik[2]])
            # Optimization
            if self._pos_1 is self._pos_0:
                rho_1 = rho_0

        return rho_0, rho_1

    def _compute(self):
        # Setup k vectors and tabulate densities
        k_sorted, k_selected = self._decimate_k()
        rho_0, rho_1 = self._tabulate_rho(k_sorted, k_selected)
        
        # Compute correlation function
        acf = [defaultdict(float) for _ in k_sorted]
        cnt = [defaultdict(float) for _ in k_sorted]
        skip = self.trajectory.block_size
        for kk, knorm in enumerate(progress(k_sorted)):
            for j in k_selected[kk]:
                ik = self.kvec[knorm][j]
                for off, i in self._discrete_tgrid:
                    for i0 in range(off, len(rho_0)-i, skip):
                        # Get the actual time difference
                        # TODO: It looks like the order of i0 and ik lopps should be swapped
                        dt = self.trajectory.steps[i0+i] - self.trajectory.steps[i0]
                        acf[kk][dt] += (rho_0[i0+i][ik] * rho_1[i0][ik].conjugate()).real #/ self._pos[i0].shape[0]
                        cnt[kk][dt] += 1

        # Normalization
        times = sorted(acf[0].keys())
        self.grid[0] = k_sorted
        self.grid[1] = [ti*self.trajectory.timestep for ti in times]
        if self._pos_0 is self._pos_1:
            # First normalize by cnt (time counts), then by value at t=0
            # We do not need to normalize by the average number of particles
            # TODO: check normalization when not GC, does not give exactly the short time behavior as pp.x
            nav = sum([p.shape[0] for p in self._pos]) / len(self._pos)
            self.value_nonorm = [[acf[kk][ti] / (cnt[kk][ti]) for ti in times] for kk in range(len(self.grid[0]))]
            self.value = [[v / self.value_nonorm[kk][0] for v in self.value_nonorm[kk]] for kk in range(len(self.grid[0]))]
        else:
            # nav_0 = sum([p.shape[0] for p in self._pos_0]) / len(self._pos_0)
            # nav_1 = sum([p.shape[0] for p in self._pos_1]) / len(self._pos_1)
            self.value_nonorm = [[acf[kk][ti] / (cnt[kk][ti]) for ti in times] for kk in range(len(self.grid[0]))]
            self.value = [[v / self.value_nonorm[kk][0] for v in self.value_nonorm[kk]] for kk in range(len(self.grid[0]))]

    def analyze(self):
        self.analysis['relaxation times tau'] = _extract_tau(self.grid[0], self.grid[1], self.value)

    def write(self):
        Correlation.write(self)
        if self._output_file != '/dev/stdout':
            with open(self._output_file + '.tau', 'w') as out:
                _write_tau(out, self.analysis)
