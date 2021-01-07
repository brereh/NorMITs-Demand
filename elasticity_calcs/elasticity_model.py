# -*- coding: utf-8 -*-
"""
    Module containing the functions for applying elasticities to the demand
    matrices.
"""

##### IMPORTS #####
# Standard imports
from pathlib import Path
from typing import List, Dict, Tuple, Union

# Third party imports
import numpy as np
import pandas as pd
from tqdm import tqdm

# Local imports
from demand_utilities.utils import get_dist_name, safe_dataframe_to_csv
from elasticity_calcs.utils import (
    read_segments_file,
    read_elasticity_file,
    get_constraint_matrices,
    read_demand_matrix,
    std_out_err_redirect_tqdm,
)
from elasticity_calcs.generalised_costs import (
    get_costs,
    gen_cost_mode,
    calculate_gen_costs,
    gen_cost_elasticity_mins,
)


##### CONSTANTS #####
SEGMENTS_FILE = "elasticity_segments.csv"
ELASTICITIES_FILE = "elasticity_values.csv"
CONSTRAINTS_FOLDER = "constraint_matrices"
# Lookup for the elasticity types and what modes/costs they affect
GC_ELASTICITY_TYPES = {
    "Car_JourneyTime": ("car", "time", 0.8),
    "Car_FuelCost": ("car", "vc", 1.2),
    "Rail_Fare": ("rail", "fare", 0.8),
    "Rail_IVTT": ("rail", "ride", 0.8),
    "Bus_Fare": ("bus", "fare", 0.8),
    "Bus_IVTT": ("bus", "ride", 0.8),
}
# ID and zone system for each mode
MODE_ID = {"car": 1, "rail": 6}
MODE_ZONE_SYSTEM = {
    "car": "norms",
    "rail": "norms",
}  # FIXME using rail demand for both for testing
COST_NAMES = "{mode}_costs_p{purpose}.csv"
OTHER_MODES = ["bus", "active", "no_travel"]


##### CLASSES #####
class ElasticityModel:
    """Class for applying elasticity calculations to EFS demand."""

    def __init__(
        self,
        input_folders: Dict[str, Path],
        output_folder: Path,
        output_years: List[int],
    ):
        self._check_folders(
            input_folders,
            (
                "elasticity",
                "translation",
                "rail_demand",
                "car_demand",
                "rail_costs",
                "car_costs",
            ),
        )

        self.elasticity_folder = input_folders["elasticity"]
        self.zone_translation_folder = input_folders["translation"]
        self.demand_folders = {
            m: [input_folders[f"{m}_{c}"] for c in ("demand", "costs")]
            for m in ("rail", "car")
        }
        self.output_folder = output_folder
        self.output_folder.mkdir(exist_ok=True)
        self.years = output_years

    @staticmethod
    def _check_folders(folders: Dict[str, Path], expected: List[str]):
        """Check if expected folders are given and exist.

        Parameters
        ----------
        folders : Dict[str, Path]
            Dictionary containing paths to the expected folders.
        expected : List[str]
            List of expected keys in the `folders` dictionary.

        Raises
        ------
        KeyError
            If any `expected` folders are missing from `folders`.
        FileNotFoundError
            If any of the paths in `folders` aren't directories.
        """
        missing = []
        not_dir = {}
        for i in expected:
            if i not in folders.keys():
                missing.append(i)
                continue
            if not folders[i].is_dir():
                not_dir[i] = folders[i]
        if missing:
            raise KeyError(f"Missing input folders: {missing}")
        if not_dir:
            raise FileNotFoundError(f"Folders could not be found: {not_dir}")

    def apply_all(self):
        segments = read_segments_file(self.elasticity_folder / SEGMENTS_FILE)
        # Redirect stdout and stderr to tqdm
        with std_out_err_redirect_tqdm() as orig_stdout:
            pbar = tqdm(
                total=len(segments) * len(self.years),
                desc="Applying elasticities to segments",
                file=orig_stdout,
                dynamic_ncols=True,
                unit="segment",
            )
            for _, row in segments.iterrows():
                for yr in self.years:
                    elasticity_params = {
                        "purpose": str(row["Elast_Purp"]),
                        "market_share": row["Elast_MarketShare"],
                    }
                    demand_params = {
                        "trip_origin": row["EFS_PurpBase"],
                        "matrix_format": "pa",
                        "year": yr,
                        "purpose": str(row["EFS_SubPurpID"]),
                    }
                    if not np.isnan(row["EFS_SkillLevel"]):
                        seg = row["EFS_SkillLevel"]
                    else:
                        seg = row["EFS_IncLevel"]
                    demand_params["segment"] = f"{seg:.0f}"
                    self.apply_elasticities(demand_params, elasticity_params)
                    pbar.update(1)
            pbar.close()

    def apply_elasticities(
        self, demand_params: Dict[str, str], elasticity_params: Dict[str, str]
    ) -> Dict[str, pd.DataFrame]:
        elasticities = read_elasticity_file(
            self.elasticity_folder / ELASTICITIES_FILE, **elasticity_params
        )
        constraint_matrices = get_constraint_matrices(
            self.elasticity_folder / CONSTRAINTS_FOLDER,
            elasticities["CstrMatrixName"].unique().tolist(),
        )
        base_demand, rail_ca_split = self._get_demand(demand_params)
        base_costs = self._get_costs(demand_params["purpose"])
        # TODO Generalised costs parameters VT/VC should be read from an input
        gc_params = {"car": {"vt": 16.58, "vc": 9.45}, "rail": {"vt": 16.6}}
        base_gc = calculate_gen_costs(base_costs, gc_params)

        # Loop through elasticity types and calculate demand adjustment
        demand_adjustment = {k: [v] for k, v in base_demand.items()}
        for elast_type in elasticities["ElasticityType"].unique():
            adj_dem = calculate_adjustment(
                base_demand,
                base_costs,
                base_gc,
                elasticities.loc[elasticities["ElasticityType"] == elast_type],
                elast_type,
                constraint_matrices,
                gc_params,
            )

            for k in demand_adjustment:
                demand_adjustment[k].append(adj_dem[k])

        # Multiply base demand by adjustments for rail and car and convert to dataframe
        adjusted_demand = {}
        for m, adjustments in demand_adjustment.items():
            adjusted_demand[m] = np.prod(adjustments, axis=0)
            if isinstance(base_demand[m], pd.DataFrame):
                adjusted_demand[m] = pd.DataFrame(
                    adjusted_demand[m],
                    columns=base_demand[m].columns,
                    index=base_demand[m].index,
                )

        # Split rail demand back into CA/NCA
        for nm, df in rail_ca_split.items():
            adjusted_demand[nm] = adjusted_demand["rail"] * df
        total_rail = adjusted_demand["ca1"] + adjusted_demand["ca2"]
        if not np.array_equal(adjusted_demand["rail"], total_rail):
            # Need to get maximum twice to get a single float
            diff = np.max(
                np.ravel(np.abs(adjusted_demand["rail"] - total_rail))
            )
            print(
                "When splitting adjusted rail demand into CA and NCA, NCA + CA "
                f"!= Total Rail, there is a maximum difference of {diff:.1E}"
            )
        adjusted_demand.pop("rail")

        # Write demand output
        self._write_demand(adjusted_demand, demand_params)
        return adjusted_demand

    def _get_demand(
        self, demand_params: Dict[str, str]
    ) -> Tuple[Dict[str, pd.DataFrame], Dict[str, np.array]]:
        """Read the rail and car demand, aggregating CA and NCA for rail.

        Parameters
        ----------
        demand_params : Dict[str, str]
            Parameters to be passed to `get_dist_name` function
            for getting the demand file name.

        Returns
        -------
        demand : Dict[str, pd.DataFrame]
            The demand data for car and rail modes read from file and
            demand values of 1 for bus, active and no_travel.
        rail_split : Dict[str, np.array]]
            The ratio of CA and NCA to total rail demand, allowing
            the demand to be split back into CA and NCA once
            elasticities are applied.

        Raises
        ------
        KeyError
            If the CA and NCA demand for rail doesn't have
            the same zone index and columns.
        """
        demand = {}
        # Get rail demand and add CA and NCA together
        m = "rail"
        tmp = {}
        for ca in ("1", "2"):
            path = self.demand_folders[m][0] / get_dist_name(
                **demand_params,
                mode=str(MODE_ID[m]),
                car_availability=ca,
                csv=True,
            )
            tmp[f"ca{ca}"] = read_demand_matrix(
                path, self.zone_translation_folder, MODE_ZONE_SYSTEM[m]
            )
        if not (
            tmp["ca1"].index.equals(tmp["ca2"].index)
            and tmp["ca1"].columns.equals(tmp["ca2"].columns)
        ):
            raise KeyError(
                get_dist_name(**demand_params, mode=MODE_ID[m])
                + " does not have the same index for CA and NCA"
            )
        # Get demand for CA + NCA and calculate split for converting back
        demand[m] = tmp["ca1"] + tmp["ca2"]
        rail_split = {}
        for k, val in tmp.items():
            rail_split[k] = np.divide(
                val.values,
                demand[m].values,
                out=np.zeros_like(val, dtype=float),
                where=demand[m] != 0,
            )
        del tmp

        # Get car demand
        m = "car"
        path = self.demand_folders[m][0] / get_dist_name(
            **demand_params, mode=str(MODE_ID[m]), csv=True
        )
        demand[m] = read_demand_matrix(
            path, self.zone_translation_folder, MODE_ZONE_SYSTEM[m]
        )

        demand.update(dict.fromkeys(OTHER_MODES, 1.0))
        return demand, rail_split

    def _get_costs(self, purpose: int) -> Dict[str, pd.DataFrame]:
        """Read the cost files for each mode in `MODE_ZONE_SYSTEM`.

        Doesn't get the costs for Bus, Active or Non-travel modes as these
        are defined as cost change in the elasticity calculations.

        Parameters
        ----------
        purpose : int
            Purpose ID to get the costs for.

        Returns
        -------
        Dict[str, pd.DataFrame]
            The costs for each mode which is present in `MODE_ID`.
        """
        costs = {}
        for m, zone in MODE_ZONE_SYSTEM.items():
            path = self.demand_folders[m][1] / COST_NAMES.format(
                mode=m, purpose=purpose
            )
            costs[m] = get_costs(path, m, zone, self.zone_translation_folder)

        costs.update(dict.fromkeys(OTHER_MODES, 1.0))
        return costs

    def _write_demand(
        self,
        adjusted_demand: Dict[str, pd.DataFrame],
        demand_params: Dict[str, str],
    ):
        """Write the adjusted demand to CSV files.

        The outputs are written to mode sub-folders in `self.output_folder`,
        the bus, active and no_travel modes are written to a single file as
        these are scalar values.

        Parameters
        ----------
        adjusted_demand : Dict[str, pd.DataFrame]
            Dictionary containing the adjusted demand for each mode.
        demand_params : Dict[str, str]
            The demand parameters to be passed to `get_dist_name` for
            creating the output filename.
        """
        for m in ("car", "ca1", "ca2"):
            ca = None
            mode = m
            if m != "car":
                ca = m[2]
                mode = "rail"
            folder = self.output_folder / mode
            folder.mkdir(parents=True, exist_ok=True)
            name = get_dist_name(
                **demand_params,
                mode=str(MODE_ID[mode]),
                car_availability=ca,
                csv=True,
            )
            safe_dataframe_to_csv(adjusted_demand[m], folder / name)

        # Write other modes to a single file
        folder = self.output_folder / "others"
        folder.mkdir(parents=True, exist_ok=True)
        name = get_dist_name(**demand_params, csv=True)
        df = pd.DataFrame(
            [
                (k, adjusted_demand[k].mean())
                for k in ("bus", "active", "no_travel")
            ],
            columns=["mode", "mean_demand_adjustment"],
        )
        safe_dataframe_to_csv(df, folder / name, index=False)


##### FUNCTIONS #####
def calculate_adjustment(
    base_demand: Dict[str, pd.DataFrame],
    base_costs: Dict[str, pd.DataFrame],
    base_gc: Dict[str, pd.DataFrame],
    elasticities: pd.DataFrame,
    elasticity_type: str,
    cost_constraint: Dict[str, np.array],
    gc_params: Dict[str, Dict[str, float]],
) -> Dict[str, np.array]:
    if elasticity_type not in GC_ELASTICITY_TYPES:
        raise KeyError(
            f"Unknown elasticity_type: '{elasticity_type}', "
            f"expected one of {list(GC_ELASTICITY_TYPES.keys())}"
        )

    chg_mode, _, _ = GC_ELASTICITY_TYPES[elasticity_type]
    # Filter only elasticities involving the mode that changes
    elasticities = elasticities.loc[
        elasticities["ModeCostChg"].str.lower() == chg_mode
    ]

    # Set base gc to 1 if it is 0 as cannot divide by 0
    tmp_base_gc = np.where(base_gc[chg_mode] == 0, 1, base_gc[chg_mode])

    # The cost and cost_factors are dependant on the cost that changes
    cost, cost_factor = _elasticity_gc_factors(
        base_costs[chg_mode],
        gc_params.get(chg_mode, {}),
        elasticity_type,
    )

    cols = ["AffectedMode", "OwnElast", "CstrMatrixName"]
    demand_adjustment = {
        m.lower(): np.full_like(base_demand[m.lower()], 1.0)
        for m in elasticities[cols[0]].unique()
    }
    for aff_mode, elast, cstr_name in elasticities[cols].itertuples(
        index=False, name=None
    ):
        aff_mode = aff_mode.lower()
        # Calculate the generalised cost of the current elasticity
        gc_elast = gen_cost_elasticity_mins(
            elast,
            base_gc[chg_mode],
            cost,
            base_demand[chg_mode],
            cost_factor,
        )
        # Adjust the costs of the change mode and calculate adjusted GC
        adj_cost, adj_gc_params = adjust_cost(
            base_costs[chg_mode],
            gc_params.get(chg_mode, {}),
            elasticity_type,
            cost_constraint[cstr_name],
        )
        adj_gc = gen_cost_mode(adj_cost, chg_mode, **adj_gc_params)
        gc_ratio = adj_gc / tmp_base_gc

        demand_adjustment[aff_mode] = demand_adjustment[aff_mode] * np.power(
            gc_ratio,
            gc_elast,
            out=np.zeros_like(gc_ratio),
            where=gc_ratio != 0,  # 0^(-x) is undefined and 0^(+x)=0 so leave 0
        )

    return demand_adjustment


def adjust_cost(
    base_costs: Union[pd.DataFrame, float],
    gc_params: Dict[str, float],
    elasticity_type: str,
    constraint_matrix: np.array = None,
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """Adjust the cost matrices or parameters for given `elasticity_type`.

    `GC_ELASTICITY_TYPES` is used as the lookup for what cost changes
    are applied.

    Parameters
    ----------
    base_costs : Union[pd.DataFrame, float]
        Base costs to be adjusted.
    gc_params : Dict[str, float]
        Generalised cost parameters to be adjusted.
    elasticity_type : str
        Elasticity type used with `GC_ELASTICITY_TYPES` lookup to
        determine the cost changes being applied.
    constraint_matrix : np.array, optional
        Constraint to be used when adjusting `base_costs`, by
        default None.

    Returns
    -------
    adj_costs : Union[pd.DataFrame, float]
        Adjusted costs, or `base_costs` if no adjustment required.
    adj_gc_params : Dict[str, float]
        Adjusted GC parameters, or `gc_params` if no adjustement
        required.

    Raises
    ------
    KeyError
        If the cost to be adjusted isn't present in the `base_costs`
        or `gc_params`.
    """
    mode, cost_type, change = GC_ELASTICITY_TYPES[elasticity_type]
    # Other modes have scalar costs and no GC params so are just
    # multiplied by change
    if not isinstance(base_costs, pd.DataFrame):
        return base_costs * change, gc_params

    # Make sure costs are sorted so that the constraint matrix lines up correctly
    adj_cost = base_costs.copy().sort_values(["origin", "destination"])
    adj_gc_params = gc_params.copy()
    if cost_type in base_costs.columns:
        if constraint_matrix is None:
            constraint_matrix = 1.0
        adj_cost[cost_type] = (
            adj_cost[cost_type] * change * constraint_matrix.flatten()
        )
    elif cost_type in gc_params:
        adj_gc_params[cost_type] = adj_gc_params[cost_type] * change
    else:
        raise KeyError(
            f"Cost type to be changed ({cost_type}) isn't present "
            f"in the base_costs or gc_params for {mode}"
        )
    return adj_cost, adj_gc_params


def _elasticity_gc_factors(
    base_costs: pd.DataFrame,
    gc_params: Dict[str, float],
    elasticity_type: str,
) -> Tuple[np.array, float]:
    """Return cost and cost_fator values for use in `gen_cost_elasticity_mins`.

    Determines the required parameters for calculating the GC elasticity
    based on the `elasticity_type` given, using `GC_ELASTICITY_TYPES` lookup.

    Parameters
    ----------
    base_costs : pd.DataFrame
        Base costs data for single mode.
    gc_params : Dict[str, float]
        Generalised cost calculation parameters for single mode.
    elasticity_type : str
        The name of the elasticity type.

    Returns
    -------
    np.array
        cost to be used in `gen_cost_elasticity_mins`.
    float
        cost_factor to be used in `gen_cost_elasticity_mins`.

    Raises
    ------
    ValueError
        If the elasticitytype given leads to an unknown combination
        of cost_type and mode.
    """
    square_matrix = lambda c: base_costs.pivot(
        index="origin", columns="destination", values=c
    )
    mode, cost_type, _ = GC_ELASTICITY_TYPES[elasticity_type]
    cost, factor = None, None
    if mode == "car":
        if cost_type == "time":
            cost = square_matrix(cost_type)
            factor = 1 / 60
        elif cost_type == "vc":
            cost = square_matrix("dist")
            factor = (gc_params["vc"] / gc_params["vt"]) / 1000
    elif mode == "rail":
        if cost_type == "ride":
            cost = square_matrix(cost_type)
        elif cost_type == "fare":
            cost = square_matrix(cost_type)
            factor = 1 / gc_params["vt"]
    elif mode in OTHER_MODES:
        cost = 1.0

    if cost is None:
        raise ValueError(
            f"Unknown cost_type/mode combination: {cost_type}, {mode} not "
            "sure what factors are required for GC elasticity calculation"
        )
    return cost, factor
