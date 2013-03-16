# Copyright (C) 2013 by Eka A. Kurniawan
# eka.a.kurniawan(ta)gmail(tod)com
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the
# Free Software Foundation, Inc.,
# 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

# References:
#  - AutoDock 4.2.3 Source Code (mkTorTree.cc, trilinterp.cc, torNorVec.cc)
#    http://autodock.scripps.edu

from Ligand import Ligand
from Protein import Protein
from Grid import Grid
from Quaternion import Quaternion

class DockingParameters:
    def __init__(self):
        # Calculate Internal Electrostatic Energies Flag
        self.calc_inter_elec_e = False

    def __repr__(self):
        ret = ""
        ret += "Calculate Internal Electrostatic Energies Flag         : %s" % \
            self.calc_inter_elec_e
        return ret

class Dock:
    def __init__(self):
        self.ligand = Ligand()
        self.protein = Protein()
        self.grid = Grid()
        # Docking Parameters
        self.dps = DockingParameters()
        # Sorted ligand and protein branches ascendingly based on number of
        # atoms in the branch
        self.sorted_branches = []
        
        # Electrostatic
        self.elecs = []
        self.elec_total = 0.0
        # Van der Waals
        self.emaps = []
        self.emap_total = 0.0

    # Rotate rotatable branches/bonds for both ligand and protein.
    # rotations is expected to be in radian.
    def rotate_branches(self, rotations):
        if not self.sorted_branches:
            for branch in self.ligand.branches:
                branch.molecule = 'l' # l for ligand
                self.sorted_branches.append(branch)
            for branch in self.protein.flex_branches:
                branch.molecule = 'p' # p for protein
                self.sorted_branches.append(branch)
            self.sorted_branches = sorted(self.sorted_branches, \
                                          key=lambda branch: len(branch.atom_ids))

        q_rotation = Quaternion()
        rot_i = 0
        for branch in self.sorted_branches:
            atoms = []
            atom_tcoords = []
            # Get the atoms from either ligand or protein based on branch
            # molecule information
            if branch.molecule == 'l':
                molecule_atoms = self.ligand.atoms
            else: # 'p'
                molecule_atoms = self.protein.flex_atoms
            # Get atom coordinates
            for atom in molecule_atoms:
                if atom.id in [branch.anchor_id] + branch.atom_ids:
                    # Anchor and link atoms are not for rotation
                    if atom.id == branch.anchor_id:
                        anchor_tcoord = atom.tcoord
                        continue
                    if atom.id == branch.link_id:
                        link_tcoord = atom.tcoord
                        continue
                    atoms.append(atom)
                    atom_tcoords.append(atom.tcoord - link_tcoord)
            # Transform
            q_rotation.set_angle_axis(rotations[rot_i], \
                                      anchor_tcoord - link_tcoord)
            new_atom_tcoords = Quaternion.transform(link_tcoord, q_rotation, \
                                                    atom_tcoords)
            for i, atom in enumerate(atoms):
                atom.tcoord = new_atom_tcoords[i]

            rot_i += 1

    # Transform (translate and rotate) ligand root (whole body)
    def transform_ligand_root(self, translation, rotation):
        atom_tcoords = self.ligand.get_atom_tcoords()
        new_atom_tcoords = Quaternion.transform(translation, rotation, \
                                                atom_tcoords)
        self.ligand.set_atom_tcoords(new_atom_tcoords)

    # 3D Linear Interpolation
    @staticmethod
    def calc_linInterp3(grid, ligand, protein):
        lo_x, lo_y, lo_z = grid.field.lo.xyz
        spacing = grid.field.spacing
        atom_len = len(ligand.atoms) + len(protein.flex_atoms)
        
        u = []
        v = []
        w = []
        for atom in ligand.atoms:
            u.append((atom.tcoord.x - lo_x) / spacing)
            v.append((atom.tcoord.y - lo_y) / spacing)
            w.append((atom.tcoord.z - lo_z) / spacing)
        for atom in protein.flex_atoms:
            u.append((atom.tcoord.x - lo_x) / spacing)
            v.append((atom.tcoord.y - lo_y) / spacing)
            w.append((atom.tcoord.z - lo_z) / spacing)

        u0 = [int(i) for i in u]
        v0 = [int(i) for i in v]
        w0 = [int(i) for i in w]
                
        u1 = [i + 1 for i in u0]
        v1 = [i + 1 for i in v0]
        w1 = [i + 1 for i in w0]
    
        p0u = [u[i] - float(u0[i]) for i in xrange(atom_len)]
        p0v = [v[i] - float(v0[i]) for i in xrange(atom_len)]
        p0w = [w[i] - float(w0[i]) for i in xrange(atom_len)]

        p1u = [float(u1[i]) - u[i] for i in xrange(atom_len)]
        p1v = [float(v1[i]) - v[i] for i in xrange(atom_len)]
        p1w = [float(w1[i]) - w[i] for i in xrange(atom_len)]

        p000 = [p0u[i] * p0v[i] * p0w[i] for i in xrange(atom_len)]
        p001 = [p0u[i] * p0v[i] * p1w[i] for i in xrange(atom_len)]
        p010 = [p0u[i] * p1v[i] * p0w[i] for i in xrange(atom_len)]
        p011 = [p0u[i] * p1v[i] * p1w[i] for i in xrange(atom_len)]
        p100 = [p1u[i] * p0v[i] * p0w[i] for i in xrange(atom_len)]
        p101 = [p1u[i] * p0v[i] * p1w[i] for i in xrange(atom_len)]
        p110 = [p1u[i] * p1v[i] * p0w[i] for i in xrange(atom_len)]
        p111 = [p1u[i] * p1v[i] * p1w[i] for i in xrange(atom_len)]

        return u0, v0, w0, u1, v1, w1, \
               p000, p001, p010, p011, p100, p101, p110, p111

    def calc_energy(self):
        u0, v0, w0, u1, v1, w1, \
            p000, p001, p010, p011, p100, p101, p110, p111 = \
            self.calc_linInterp3(self.grid, self.ligand, self.protein)

        atom_len = len(self.ligand.atoms) + len(self.protein.flex_atoms)
                
        es = [] # Electrostatic
        for i in xrange(atom_len):
            e = 0.0
            e += p000[i] * self.grid.maps['e'][w1[i]][v1[i]][u1[i]]
            e += p001[i] * self.grid.maps['e'][w1[i]][v1[i]][u0[i]]
            e += p010[i] * self.grid.maps['e'][w1[i]][v0[i]][u1[i]]
            e += p011[i] * self.grid.maps['e'][w1[i]][v0[i]][u0[i]]
            e += p100[i] * self.grid.maps['e'][w0[i]][v1[i]][u1[i]]
            e += p101[i] * self.grid.maps['e'][w0[i]][v1[i]][u0[i]]
            e += p110[i] * self.grid.maps['e'][w0[i]][v0[i]][u1[i]]
            e += p111[i] * self.grid.maps['e'][w0[i]][v0[i]][u0[i]]
            es.append(e)

        ds = [] # Desolvation
        for i in xrange(atom_len):
            d = 0.0
            d += p000[i] * self.grid.maps['d'][w1[i]][v1[i]][u1[i]]
            d += p001[i] * self.grid.maps['d'][w1[i]][v1[i]][u0[i]]
            d += p010[i] * self.grid.maps['d'][w1[i]][v0[i]][u1[i]]
            d += p011[i] * self.grid.maps['d'][w1[i]][v0[i]][u0[i]]
            d += p100[i] * self.grid.maps['d'][w0[i]][v1[i]][u1[i]]
            d += p101[i] * self.grid.maps['d'][w0[i]][v1[i]][u0[i]]
            d += p110[i] * self.grid.maps['d'][w0[i]][v0[i]][u1[i]]
            d += p111[i] * self.grid.maps['d'][w0[i]][v0[i]][u0[i]]
            ds.append(d)

        ms = [] # Atom Type
        for i, atom in enumerate(self.ligand.atoms):
            m = 0.0
            type = atom.type
            m += p000[i] * self.grid.maps[type][w1[i]][v1[i]][u1[i]]
            m += p001[i] * self.grid.maps[type][w1[i]][v1[i]][u0[i]]
            m += p010[i] * self.grid.maps[type][w1[i]][v0[i]][u1[i]]
            m += p011[i] * self.grid.maps[type][w1[i]][v0[i]][u0[i]]
            m += p100[i] * self.grid.maps[type][w0[i]][v1[i]][u1[i]]
            m += p101[i] * self.grid.maps[type][w0[i]][v1[i]][u0[i]]
            m += p110[i] * self.grid.maps[type][w0[i]][v0[i]][u1[i]]
            m += p111[i] * self.grid.maps[type][w0[i]][v0[i]][u0[i]]
            ms.append(m)

        # Electrostatic
        self.elecs = []
        self.elec_total = 0.0
        for i, atom in enumerate(self.ligand.atoms):
            self.elec = es[i] * atom.charge
            self.elecs.append(self.elec)
            self.elec_total += self.elec

        # Van der Waals
        self.emaps = []
        self.emap_total = 0.0
        for i, atom in enumerate(self.ligand.atoms):
            self.emap = ms[i] + ds[i] * abs(atom.charge)
            self.emaps.append(self.emap)
            self.emap_total += self.emap

    def test_print(self):
        for i, atom in enumerate(self.ligand.atoms):
            print "%2s: %2s - %8.3f, %8.3f, %8.3f | %+7.2f | %+7.2f" % \
                (i + 1, atom.type, \
                 atom.tcoord.x, atom.tcoord.y, atom.tcoord.z, \
                 self.emaps[i], self.elecs[i])
        for i, atom in enumerate(self.protein.flex_atoms):
            print "%2s: %2s - %8.3f, %8.3f, %8.3f | %+7.2f | %+7.2f" % \
                (i + 1, atom.type, \
                 atom.tcoord.x, atom.tcoord.y, atom.tcoord.z, \
                 self.emaps[i], self.elecs[i])


#bar - start
#dpf = DPF("./Parameters/ind.dpf")
#print dpf.about
#bar - stop