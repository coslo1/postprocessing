#!/usr/bin/env python
# This file is part of atooms
# Copyright 2010-2014, Daniele Coslovich

"""
Common neighbor analysis.

Bonds are identified by a signature (i,j,k), where 
i: particle species (1 by default)
j: number of common neighbors
k: number of of bonds between common neighbors

For instance, icosahedral bonds are 1,5,5.
"""

import os
import sys
import argparse
from collections import defaultdict
from atooms.trajectory import Trajectory, TrajectoryNeighbors
from atooms.plugins.voronoi import TrajectoryVoronoi
from atooms.utils import add_first_last_skip, fractional_slice
from pyutils.histogram import Histogram
from atooms.plugins.neighbors import all_neighbors, get_neighbors


def cna(particle, neighbors):
    # Add neighbor list to particles as sets
    for p, n in zip(particle, neighbors):
        p.neighbors = set(n)

    # For all i-j pairs find mutual CNA index
    data = []
    for i in range(len(particle)):
        ni = particle[i].neighbors
        for j in ni:
            if j<=i: continue
            nj = particle[j].neighbors
            # Mutual neighbors of i-j pair
            common = ni & nj
            # Count bonds between mutual neighbors
            bonds = 0
            for k in common:
                for m in common:
                    if m<=k: continue
                    if m in particle[k].neighbors:
                        bonds+=1
            # Accumulate CNA index
            #print 'cna (%s,%s): %d_%d_%d' % (i,j,1,len(common),bonds)
            data.append('%d_%d_%d' % (1,len(common),bonds))
    return data

def main(t, tn):
    cna(t[0].particle, [v.neighbors for v in tn[0].voronoi])

parser = argparse.ArgumentParser()
parser = add_first_last_skip(parser, what=['first', 'last'])
parser.add_argument('-n',              dest='neigh_file', type=str, default='', help='neighbors file')
parser.add_argument('-N', '--neighbor',dest='neigh', type=str, default='', help='flags for neigh.x command')
parser.add_argument('-V', '--neighbor-voronoi',dest='neigh_voronoi', action='store_true', help='neigh_file is of Voronoi type')
parser.add_argument('-M', '--neighbor-max',dest='neigh_limit', type=int, default=None, help='take up to *limit* neighbors (assuming they are ordered)')
parser.add_argument('-s', '--signature',dest='signature', action='store', default=None, help='signature')
parser.add_argument('-o', '--output',dest='output', action='store_true', help='write to file')
parser.add_argument('-t', '--tag',     dest='tag', type=str, default='', help='tag to add before suffix')
parser.add_argument(nargs='+', dest='files',type=str, help='input files')
args = parser.parse_args()

if len(args.tag) > 0:
    args.tag = '_' + args.tag

# Handle multiple signatures: make a list of them
if args.signature is not None:
    args.signature = args.signature.split(',')

for finp in args.files:
    t = Trajectory(finp)
    tn, desc = get_neighbors(finp, args, os.path.basename(sys.argv[0]))

    # Fraction of selected CNA bonds (signature argument)
    if args.signature is not None:
        fh = dict()
        for sign in args.signature:
            fout = finp + '.cna%s.fraction-%s' % (args.tag, sign)
            fh[sign] = open(fout, 'w', buffering=0)
            fh[sign].write('# Fraction of CNA bond %s; neighbors: %s\n' % (sign, desc))

    # Loop over samples
    hist = defaultdict(int)
    for i, s in enumerate(t):
        if t.steps[i] in tn.steps:
            ii = tn.steps.index(t.steps[i])
            data = cna(t[i].particle, tn[ii].neighbors)
            # Dump signature
            if args.signature is not None:
                for sign in args.signature:
                    x = len([d for d in data if d == sign]) / float(len(data))
                    fh[sign].write('%d %s\n' % (t.steps[i], x))
            # Fill histogram
            for d in data:
                hist[d]+=1

    # Write histogram
    with open(finp + '.cna%s.hist' % args.tag, 'w') as fhhist:
        norm = sum(hist.values())
        fhhist.write('# CNA bonds histogram; neighbors: %s\n' % desc)
        for d in sorted(hist, key=hist.get, reverse=True):
            fhhist.write('%s %g\n' % (d, hist[d] / float(norm)))

    if args.signature is not None:
        for fhi in fh.values():
            fhi.close()

    if len(args.neigh_file)==0:
        os.remove(tn.filename)
