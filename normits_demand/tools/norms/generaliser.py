# -*- coding: utf-8 -*-
"""
Created on: 10/05/2022
Updated on:

Original author: Ben Taylor
Last update made by:
Other updates made by:

File purpose:
Module to take NoRMS output matrices and generalise them into a standard
format where they can be picked up by other models
"""
# Built-Ins
import os
import pathlib
import dataclasses

# Third Party

# Local Imports
import pandas as pd

from normits_demand import core as nd_core
from normits_demand import logging as nd_log
from normits_demand.tools.norms import tp_proportion_extractor
from normits_demand.tools.norms import tp_proportion_converter


LOG = nd_log.get_logger(f"{nd_log.get_package_logger_name()}.norms_generaliser")


@dataclasses.dataclass
class NormsTpProportionFiles:
    """Store the filenames of all CUBE tour proportion file names"""

    home_dir: pathlib.Path
    extracted_pickle_fname: str = "norms_time_period_proportions.pkl"

    # Home-based tour proportions
    hb_internal_business_fname: str = "SplitFactors_D1.mat"
    hb_internal_commute_fname: str = "SplitFactors_D2.mat"
    hb_internal_other_fname: str = "SplitFactors_D3.mat"

    # Non-home-based time period splitting factors
    nhb_internal_split_factors_fnames = {
        1: "OD_Prop_AM_PT.mat",
        2: "OD_Prop_IP_PT.mat",
        3: "OD_Prop_PM_PT.mat",
        4: "OD_Prop_OP_PT.mat",
    }

    external_split_factors_fnames = {
        1: "Time_of_Day_Factors_Zonal_AM.mat",
        2: "Time_of_Day_Factors_Zonal_IP.mat",
        3: "Time_of_Day_Factors_Zonal_PM.mat",
        4: "Time_of_Day_Factors_Zonal_OP.mat",
    }

    def get_extracted_pickle_path(self):
        """Build and return the path for the extracted pickle data"""
        return self.home_dir / self.extracted_pickle_fname

    def all_files_exist(self, throw_error: bool = False) -> bool:
        """Check if all files listed in this object exist

        Parameters
        ----------
        throw_error:
            Whether to throw and error when a file doesn't exist or not.t

        Returns
        -------
        all_files_exist:
            A boolean stating whether all the files listed in this object
            exist or not.
        """
        check_files = [
            self.hb_internal_business_fname,
            self.hb_internal_commute_fname,
            self.hb_internal_other_fname,
        ]
        check_files += list(self.nhb_internal_split_factors_fnames.values())
        check_files += list(self.external_split_factors_fnames.values())

        for fname in check_files:
            if not (self.home_dir / fname).exists():
                if throw_error:
                    raise ValueError(
                        "Not all the expected files exist. At least one file "
                        f"is missing. Cannot find '{self.home_dir / fname}'."
                    )
                return False

        return True


class NoRMSPostMeTpProportions:
    """Extraction and conversion of NoRMS tour proportions from CUBE"""

    def __init__(self, tour_prop_import: os.PathLike):
        tour_prop_pickle = pd.read_pickle(tour_prop_import)
        self.zoning_system = nd_core.get_zoning_system("norms")

        # Convert the dictionary into its component parts
        fh_th_factors = tp_proportion_converter.convert_tour_proportions(
            tour_prop_pickle,
            self.zoning_system,
        )
        self.internal_fh_factors = fh_th_factors[0]
        self.internal_th_factors = fh_th_factors[1]
        print(self.internal_th_factors.keys())
        print(self.internal_th_factors[1].keys())
        print(self.internal_th_factors[1][1].keys())
        print(self.internal_th_factors[1][1][1])
        print(self.internal_th_factors[1][1][1].shape)

        self.internal_tp_split_factors = (
            tp_proportion_converter.convert_internal_tp_split_factors(
                tour_prop_pickle,
                self.zoning_system,
            )
        )
        print(self.internal_tp_split_factors.keys())
        print(self.internal_tp_split_factors[12].keys())
        print(self.internal_tp_split_factors[12][1].keys())
        print(self.internal_tp_split_factors[12][1][1])
        print(self.internal_tp_split_factors[12][1][1].shape)

        self.external_tp_split_factors = (
            tp_proportion_converter.convert_external_tp_split_factors(
                tour_prop_pickle,
                self.zoning_system,
            )
        )


def get_norms_post_me_tp_proportions(
    norms_files: NormsTpProportionFiles,
    overwrite_extracted_pickle: bool = False,
) -> NoRMSPostMeTpProportions:
    """Create a NoRMSInternalPostMETourProportions object

    Checks what data is available and what steps have already been completed
    in `import_path` before creating a NoRMSInternalPostMETourProportions object.
    If the tour proportions have already been extracted from CUBE, then
    it will not be repeated, unless explicitly told to. Otherwise the data
    will be converted

    Parameters
    ----------
    norms_files:
        A NormsTpProportionFiles object stating where all the files
        needed to generate the time period proportions should be.

    overwrite_extracted_pickle:
        Whether to overwrite the data extracted from CUBE if it already exists.

    Returns
    -------

    """
    # Decide if we need to extract data from CUBE or not
    extracted_pickle_path = norms_files.get_extracted_pickle_path()
    if overwrite_extracted_pickle or not extracted_pickle_path.exists():
        # Create the pickle again
        LOG.info("Extracting time period proportions from CUBE")
        tp_proportion_extractor.main(
            norms_files.home_dir,
            extracted_pickle_path,
        )

    return NoRMSPostMeTpProportions(tour_prop_import=extracted_pickle_path)
