# This file is part of atooms
# Copyright 2010-2014, Daniele Coslovich

import sys
import os
import copy
import numpy
import math
import random
import warnings
import logging
from collections import defaultdict


def filter_species(system, i):
    s = copy.copy(system)
    s.particle = [p for p in system.particle if p.id == i]
    return s

def filter_all(system):
    s = copy.copy(system)
    s.particle = [p for p in system.particle]
    return s

def adjust_skip(trajectory, n_origin=-1):
    """ Utility function to set skip so as to keep computation time under control """
    # TODO: We should also adjust it for Npart
    if trajectory.block_period > 1:
        return trajectory.block_period
    else:
        if n_origin > 0:
            return max(1, int(len(trajectory.steps) / float(n_origin)))
        else:
            return 1

def acf(grid, skip, t, x):
    """Auto correlation function.
    Calculate the correlation between time t(i0) and t(i0+i) 
    for all possible pairs (i0,i) provided by grid.
    """
    acf = defaultdict(float)
    cnt = defaultdict(int)
    xave = numpy.average(x)
    for i in grid:
        for i0 in range(0, len(x)-i, skip):
            # Get the actual time difference
            dt = t[i0+i] - t[i0]
            acf[dt] += (x[i0+i]-xave) * (x[i0]-xave)
            cnt[dt] += 1

    # Return the ACF with the time differences sorted 
    dt = sorted(acf.keys())
    return dt, [acf[t] / cnt[t] for t in dt], cnt

def gcf(f, grid, skip, t, x):
    """Generalized correlation function.
    Pass a function to apply to the data.
    Exemple: mean square displacement.
    """
    # Calculate the correlation between time t(i0) and t(i0+i) 
    # for all possible pairs (i0,i) provided by grid
    acf = defaultdict(float)
    cnt = defaultdict(int)
    for i in grid:
        # Note: len(x) gives x.shape[0]
        for i0 in xrange(0, len(x)-i-1, skip):
            # Get the actual time difference
            dt = t[i0+i] - t[i0]
            acf[dt] += f(x[i0+i], x[i0])
            cnt[dt] += 1

    # Return the ACF with the time differences sorted 
    dt = sorted(acf.keys())
    return dt, [acf[t] / cnt[t] for t in dt], [cnt[t] for t in dt]

def gcf_offset(f, grid, skip, t, x):
    """Generalized correlation function.
    Pass a function to apply to the data.
    Exemple: mean square displacement.
    """
    # Calculate the correlation between time t(i0) and t(i0+i) 
    # for all possible pairs (i0,i) provided by grid
    acf = defaultdict(float)
    cnt = defaultdict(int)
    for off, i in grid:
        for i0 in xrange(off, len(x)-i-skip, skip):
            # Get the actual time difference
            dt = t[i0+i] - t[i0]
            acf[dt] += f(x[i0+i], x[i0])
            cnt[dt] += 1

    # Return the ACF with the time differences sorted 
    dt = sorted(acf.keys())
    return dt, [acf[t] / cnt[t] for t in dt] #, [cnt[t] for t in dt]

def gcf_offset_bin(f, grid, skip, t, x):
    """Generalized correlation function.
    Pass a function to apply to the data.
    Exemple: mean square displacement.
    """
    # Calculate the correlation between time t(i0) and t(i0+i) 
    # for all possible pairs (i0,i) provided by grid
    from pyutils.histogram import Histogram
    acf = Histogram()
    for off, i in grid:
        for i0 in xrange(off, len(x)-i-skip, skip):
            acf.add([(t[i0+i] - t[i0], f(x[i0+i], x[i0]) / 0.1)])

    # Return the ACF with the time differences sorted 
    fh = open('/tmp/2', 'w')
    for x, y, in zip(acf.grid, acf.frequency):
        fh.write('%g %g %g\n' % (x[0], x[1], y))
    fh.close()
    import sys
    sys.exit()
    return acf.grid, acf.value

# this seems to fit well as a trajectory method...
def _setup_t_grid(trajectory, t_grid):

    #from pyutils.utils import templated

    def templated(entry, template, keep_multiple=False):
        """Filter a list of entries so as to best match an input template. Lazy, slow version O(N*M).
        Ex.: entry=[1,2,3,4,5,10,20,100], template=[1,7,12,80] should return [1,5,10,100]."""
        match = [min(entry, key=lambda x : abs(x-t)) for t in template]
        if not keep_multiple:
            match = list(set(match))
        return sorted(match)

    # First get all possible time differences
    steps = trajectory.steps
    off_samp = {}
    for off in range(trajectory.block_period):
        for i in range(off, len(steps)-off):
            if not steps[i] - steps[off] in off_samp:
                off_samp[steps[i] - steps[off]] = (off, i-off)
                
    # Retain only those pairs of offsets and sample
    # difference that match the desired input. This is the grid
    # used internally to calculate the time correlation function.
    i_grid = set([int(round(t/trajectory.timestep)) for t in t_grid])
    offsets = [off_samp[t] for t in templated(sorted(off_samp.keys()), sorted(i_grid))]
    return offsets


# Remember log level is DEBUG < INFO < ERROR
LOG_LEVEL = 'ERROR'
UPDATE = False

class Correlation(object):

    log = None
    nbodies = 1
   
    def __init__(self, trj, grid, name="", short_name="", description="", phasespace=[]):
        # TODO: we could force trajectory cast if a string is passed
        self.trajectory = trj
        self.grid = grid
        self.name = name
        self.short_name = short_name
        self.description = description
        self.results = {}
        self.output = None
        self._phasespace = phasespace
        self.prefix = 'pp'
        self.tag = ''
        self.comments = None # can be modified by user at run time
        if isinstance(phasespace, str):
            self._phasespace = [phasespace]
        self.cbk = []
        self.cbk_args = []
        self.cbk_kwargs = []

        # If update mode is on, we will only do the calculation if the trajectory
        # file is newer than any of the provided files
        self._need_update = True
        if UPDATE:
            if os.path.exists(self._output_file):
                if os.path.getmtime(self.trajectory.filename) < os.path.getmtime(self._output_file):
                    self._need_update = False
                    # # TODO: to optimize avoid reading correlation objects unless we explicitly pass something to __init__
                    # # We source the existing file
                    # self._read()

        # TODO: logging interferes with atooms 
        # Create logger
        # log_level = getattr(logging, LOG_LEVEL)
        # if self.log is None: # or log_level != logging.getLogger().level:
        #     logging.basicConfig(format="%(levelname)s:%(asctime)s: %(message)s", level=log_level, datefmt='%d/%m/%Y %H:%M')
        #     self.log = logging.getLogger()

        # Log
        # if not self._need_update:
        #     self.log.info('[%s] skipping %s' % (short_name, self.trajectory.filename))
        # else:
        #     self.log.info('[%s] processing %s' % (short_name, self.trajectory.filename))

    def add_filter(self, cbk, *args, **kwargs):
        if len(self.cbk) > self.nbodies:
            raise ValueError('number of filters cannot exceed n. of bodies')
        self.cbk.append(cbk)
        self.cbk_args.append(args)
        self.cbk_kwargs.append(kwargs)

    def _setup_arrays(self):
        """Dump positions and/or velocities in numpy array"""
        if self.nbodies == 1:
            self._setup_arrays_onebody()
        elif self.nbodies == 2:
            self._setup_arrays_twobody()

    def _setup_arrays_onebody(self):
        self._pos = []
        self._vel = []
        if 'pos' in self._phasespace or 'vel' in self._phasespace:
            for s in self.trajectory:
                # Apply filter if there is one
                if len(self.cbk) > 0:
                    s = self.cbk[0](s, *self.cbk_args[0], **self.cbk_kwargs[0])
                if 'pos' in self._phasespace:
                    self._pos.append(s.dump('pos'))
                if 'vel' in self._phasespace:
                    self._vel.append(s.dump('vel'))

        # Dump unfolded positions if requested
        self._pos_unf = []
        if 'pos-unf' in self._phasespace:
            for s in trajectory.Unfolded(self.trajectory):
                # Apply filter if there is one
                if len(self.cbk) > 0:
                    s = self.cbk[0](s, *self.cbk_args[0], **self.cbk_kwargs[0])
                self._pos_unf.append(s.dump('pos'))

        # If trajectory is grandcanonical, we make sure all samples
        # have non-zero particles and raise an exception.
        for data in [self._pos]:
            if len(data) > 0:
                if 0 in [len(p) for p in self._pos]:
                    raise ValueError('cannot handle null samples in GC trajectory')

    def _setup_arrays_twobody(self):
        if len(self.cbk) <= 1:
            self._setup_arrays_onebody()
            self._pos_0 = self._pos
            self._pos_1 = self._pos
            return

        self._pos_0, self._pos_1 = [], []
        self._vel_0, self._vel_1 = [], []
        if 'pos' in self._phasespace or 'vel' in self._phasespace:
            for s in self.trajectory:
                s0 = self.cbk[0](s, *self.cbk_args[0], **self.cbk_kwargs[0])
                s1 = self.cbk[1](s, *self.cbk_args[1], **self.cbk_kwargs[1])
                if 'pos' in self._phasespace:
                    self._pos_0.append(s0.dump('pos'))
                    self._pos_1.append(s1.dump('pos'))
                if 'vel' in self._phasespace:
                    self._vel_0.append(s0.dump('vel'))
                    self._vel_1.append(s1.dump('vel'))

        # Dump unfolded positions if requested
        self._pos_unf_0, self._pos_unf_1  = [], []
        if 'pos-unf' in self._phasespace:
            for s in trajectory.Unfolded(self.trajectory):
                s0 = self.cbk[0](s, *self.cbk_args[0], **self.cbk_kwargs[0])
                s1 = self.cbk[1](s, *self.cbk_args[1], **self.cbk_kwargs[1])
                self._pos_unf_0.append(s0.dump('pos'))
                self._pos_unf_1.append(s1.dump('pos'))

        # If trajectory is grandcanonical, we make sure all samples
        # have non-zero particles and raise an exception.
        for data in [self._pos_0, self._pos_1]:
            if 0 in [len(p) for p in data]:
                raise ValueError('cannot handle null samples in GC trajectory')

    def compute(self):
        if not self._need_update:
            return
        self._setup_arrays()
        self._compute()
        try:
            self.analyze()
        except ImportError as e:
            print 'Could not analyze due to missing modules, continuing...'
            print e.message
        return self.grid, self.value
        
    def _compute(self):
        pass

    def analyze(self):
        pass

    @property
    def _output_file(self):
        filename = '.'.join([e for e in [self.trajectory.filename, self.prefix, self.short_name, self.tag] if len(e)>0])
        # always remove trailing dot (this allows directories)
        filename = filename.replace('/.', '/')
        return filename

    def read(self):
        try:
            inp = open(self._output_file, 'r')
        except IOError:
            self.log.error("could not find file %s" % self._output_file)

        x = numpy.loadtxt(inp, unpack=True)
        if len(x) == 3:
            self.grid, self.value = x
        elif len(x) == 2:
            self.grid, self.value = x
        else:
            self.grid, self.value = x[0:2]
            warnings.warn("Ignoring some columns in %s" % self._output_file)

        inp.close()

    def write(self, value=None):
        # We can pass a different value
        if value is None:
            value = self.value

        # TODO: it is probably the compute method that should be responsible for dumping grids appropriately, this would make the work here easier. Grouping with \n\n can be done with bash group
        if len(self.grid) == 2:
            x = numpy.array(self.grid[0]).repeat(len(value[0]))
            y = numpy.array(self.grid[1] * len(self.grid[0]))
            z = numpy.array(value).flatten()
            dump = numpy.transpose(numpy.array([x, y, z]))
        else:
            dump = numpy.transpose(numpy.array([self.grid, value]))
        
        comments='# %s (%s)\n' % (self.description, self.tag)
        if not self.comments is None:
            comments += self.comments

        # comments is not available in old numpy (< 1.7)
#        numpy.savetxt(self._output_file, dump, fmt="%g", comments=comments)
        fh = open(self._output_file, 'w')
        fh.write(comments)
        numpy.savetxt(fh, dump, fmt="%g")
        fh.close()
        
        # Analysis results
        if len(self.results) == 0:
            return

        out = open(self._output_file + '.info', 'w')
        for x, f in self.results.iteritems():
            if f is not None:
                out.write('%s = %s\n' % (x, f))
        out.close()

    def do(self):
        if not self._need_update:
            return
        self.compute()
        try:
            self.analyze()
        except ImportError as e:
            print 'Could not analyze due to missing modules, continuing...'
            print e.message
        self.write()

    def do_dims(self):
        for i in range(self.trajectory.read(0).number_of_dimensions):
            self.do(tag='dim%i' % (i+1), dim=slice(i, i+1, None))


class CorrelationTemplate(Correlation):
    
    def __init__(self, trajectory, grid, name, description=""):
        super().__init__(self, trajectory, tgrid, 't', '')

    def compute(self):
        pass

    def analyze(self):
        pass

    def write(self):
        pass
                       




                        