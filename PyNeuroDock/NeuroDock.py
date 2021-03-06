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
#  - AutoDock 4.2.3 Source Code (main.cc, parse_dpf_line.cc, dpftoken.h)
#    http://autodock.scripps.edu
#  - Program arguments handler
#    http://www.artima.com/weblogs/viewpost.jsp?thread=4829

import sys
import getopt
from Grid import Field
from Dock import Dock, DockOpenCL
from Map import ElectrostaticMap, DesolvationMap, AtomTypeMap
from Axis3 import Axis3
import Optimization

class NeuroDock:
    def __init__(self, docking_parameter_file = None):
        self.docking_parameter_file = docking_parameter_file
        self.dock = None
        self.optimization = None
        self.accelerator = ""
        self.cl_device_type = ""
        
        self.grid_field_file = ""
        self.atom_type_map_files = {}
        self.electrostatic_map_file = ""
        self.desolvation_map_file = ""
        self.ligand_file = ""
        self.protein_file = ""

    def run(self):
        with open(self.docking_parameter_file, 'r') as p_file:
            for line in p_file:
                if line.startswith("intelec"):
                    self.dock.dps.calc_inter_elec_e = True

                # Atomic bonding parameter file
                if line.startswith("b_prm"):
                    self.dock.bond.read(line.split()[1])

                if line.startswith("ligand_types"):
                    for type in line.split('#')[0].split()[1:]:
                        self.dock.ligand.atom_types.append(type)
                        self.atom_type_map_files[type] = ""
                    self.dock.bond.calc_internal_energy_tables(self.dock.ligand)

                if line.startswith("fld"):
                    self.grid_field_file = "./Parameters/" + line.split()[1]
                    self.dock.grid.field = Field(self.grid_field_file)

                if line.startswith("map"):
                    filename = line.split()[1]
                    type = filename.split('.')[1]
                    self.atom_type_map_files[type] = "./Maps/" + filename
                    self.dock.grid.maps[type] = AtomTypeMap(self.atom_type_map_files[type], self.dock.grid.field).map

                if line.startswith("elecmap"):
                    self.electrostatic_map_file = "./Maps/" + line.split()[1]
                    self.dock.grid.maps['e'] = ElectrostaticMap(self.electrostatic_map_file, self.dock.grid.field).map

                if line.startswith("desolvmap"):
                    self.desolvation_map_file = "./Maps/" + line.split()[1]
                    self.dock.grid.maps['d'] = DesolvationMap(self.desolvation_map_file, self.dock.grid.field).map

                # Set movable molecule (ligand)
                if line.startswith("move"):
                    self.ligand_file = "./Inputs/" + line.split()[1]
                    self.dock.ligand.read_pdbqt(self.ligand_file)

                # Set flexible portion of molecule (normally protein receptor)
                if line.startswith("flexres"):
                    self.protein_file = "./Inputs/" + line.split()[1]
                    self.dock.protein.read_flex_pdbqt(self.protein_file)

                if line.startswith("about"):
                    about = Axis3(0.0, 0.0, 0.0)
                    about.xyz = [float(axis) for axis in line.split()[1:4]]
                    self.dock.ligand.about = about
                    # Zero-out central point. Applicable only for all ligand
                    # atoms (not protein atoms)
                    for i in xrange(len(self.dock.ligand.ori_atoms)):
                        self.dock.ligand.ori_atoms[i].tcoord -= about
                    self.dock.ligand.reset_atoms()

                # Pre-energy calculation
                if line.startswith("pre_energy_calc"):
                    # Get atomic non-bond lists
                    self.dock.get_non_bond_list()

                    # Calculate binding torsional free energy
                    self.dock.torsional_energy = self.dock.bond.torsional_dof * \
                                                 self.dock.bond.fec_tors

                # --------------------------------------- Empirical Settings ---
                # 1-4 interactions
                if line.startswith("include_1_4_interactions"):
                    # By default, 1-4 interactions is disabled. Only 1-1, 1-2,
                    # and 1-3 interactions are considered.
                    self.dock.bond.include_1_4_interactions = True

                # Torsional degrees of freedom (DoF)
                if line.startswith("torsdof"):
                    self.dock.bond.torsional_dof = int(line.split()[1])

                #---------------------------------------------- Optimization ---
                # Define optimization type to use
                if line.startswith("opt_type"):
                    type = line.split()[1]
                    if type == "ga":
                        if self.accelerator == "sequential":
                            self.optimization = \
                                Optimization.GeneticAlgorithm(self.dock)
                        if self.accelerator == "opencl":
                            self.optimization = \
                                Optimization.GeneticAlgorithmOpenCL(self.dock, \
                                                                    self.cl_device_type)

                # Run optimization
                if line.startswith("opt_run"):
                    self.optimization.run()

                #------------------------------------ Opt: Genetic Algorithm ---
                if line.startswith("opt_ga"):
                    words = line.split()
                    type = words[1]
                    value = words[2]
                    if type == "community_size":
                        self.optimization.community_size = int(value)
                    if type == "pop_size":
                        self.optimization.population_size = int(value)
                    if type == "num_generations":
                        self.optimization.num_gen = int(value)

                #----------------------------------------------- Accelerator ---
                # Define parallel processing accelerator
                if line.startswith("accelerator"):
                    self.accelerator = line.split()[1]
                    if self.accelerator == "sequential":
                        self.dock = Dock()
                    if self.accelerator == "opencl":
                        self.dock = DockOpenCL()

                # Define OpenCL device types
                if line.startswith("ocl_device_type"):
                    self.cl_device_type = line.split()[1]

class Usage(Exception):
    def __init__(self, msg):
        self.msg = msg

def main(argv = None):
    docking_parameter_file = ""         # docking parameter file

    if argv is None:
        argv = sys.argv
    try:
        try:
            opts, args = getopt.getopt(argv[1:], "hp:", ["help"])
        except getopt.error, msg:
            raise Usage(msg)

        for o, a in opts:
            if o in ("-h", "--help"):
                print "To run, execute: " + \
                      "python NeuroDock.py -p docking_parameter_file.dpf"
                sys.exit(0)
            if o in ("-p"):
                docking_parameter_file = a

        if docking_parameter_file == "":
            docking_parameter_file = "./Parameters/ind.dpf"
        neuroDock = NeuroDock(docking_parameter_file)
        neuroDock.run()

    except Usage, err:
        print >>sys.stderr, err.msg
        print >>sys.stderr, "for help use --help"
        return 2

if __name__ == "__main__":
    sys.exit(main())

