# -*- coding: utf-8 -*-
"""
Created on: Fri September 11 12:46:25 2020
Updated on:

Original author: Ben Taylor
Last update made by:
Other updates made by:

File purpose:
Collection of functions for translating PA matrices into OD matrices.
TODO: After integrations with TMS, combine with pa_to_od.py
  to create a general pa_to_od.py file

"""

import numpy as np
import pandas as pd

from typing import Any
from typing import List
from typing import Dict
from itertools import product

from tqdm import tqdm

# self imports
from normits_demand import efs_constants as consts
from normits_demand.utils import general as du
from normits_demand.concurrency import multiprocessing

# Can call tms pa_to_od.py functions from here
# TODO: Fix old_tms import
from normits_demand.utils.old_tms.pa_to_od import *


def simplify_time_period_splits(time_period_splits: pd.DataFrame):
    """
    Simplifies time_period_splits to a case where the purpose_from_home
    is always the same as the purpose_to_home

    Parameters
    ----------
    time_period_splits:
        A time_period_splits dataframe extracted using get_time_period_splits()

    Returns
    -------
    time_period_splits only where the purpose_from_home
    is the same as purpose_to_home
    """
    time_period_splits = time_period_splits.copy()

    # Problem column doesn't exist in this case
    if 'purpose_to_home' not in time_period_splits.columns:
        return time_period_splits

    # Build a mask where purposes match
    unq_purpose = time_period_splits['purpose_from_home'].drop_duplicates()
    keep_rows = np.array([False] * len(time_period_splits))
    for p in unq_purpose:
        purpose_mask = (
            (time_period_splits['purpose_from_home'] == p)
            & (time_period_splits['purpose_to_home'] == p)
        )
        keep_rows = keep_rows | purpose_mask

    time_period_splits = time_period_splits.loc[keep_rows]

    # Filter down to just the needed col and return
    needed_cols = [
        'purpose_from_home',
        'time_from_home',
        'time_to_home',
        'direction_factor']
    return time_period_splits.reindex(needed_cols, axis='columns')


def _build_tp_pa_internal(pa_import,
                          pa_export,
                          matrix_format,
                          year,
                          purpose,
                          mode,
                          segment,
                          car_availability,
                          tp_import
                          ):
    """
    The internals of build_tp_pa(). Useful for making the code more
    readable due to the number of nested loops needed

    Returns
    -------
    None
    """
    # ## READ IN TIME PERIOD SPLITS FILE ## #
    if purpose in consts.ALL_NHB_P:
        tp_split_fname = 'export_nhb_productions_norms.csv'
        tp_split_path = os.path.join(tp_import, tp_split_fname)
        trip_origin = 'nhb'
        model_zone = 'o_zone'
    elif purpose in consts.ALL_HB_P:
        tp_split_fname = 'export_productions_norms.csv'
        tp_split_path = os.path.join(tp_import, tp_split_fname)
        trip_origin = 'hb'
        model_zone = 'p_zone'
    else:
        raise ValueError(
            "%s is neither a home based nor non-home based purpose."
            % str(purpose)
        )

    # Read in the seed values for tp splits
    tp_split = pd.read_csv(tp_split_path).rename(
        columns={
            'norms_zone_id': model_zone,
            'p': 'purpose_id',
            'm': 'mode_id',
            'soc': 'soc_id',
            'ns': 'ns_id',
            'ca': 'car_availability_id',
            'time': 'tp'
        }
    )
    tp_split[model_zone] = tp_split[model_zone].astype(int)

    # Aggregate to p/m if NHB
    if trip_origin == 'nhb':
        tp_split = tp_split.groupby(
            [model_zone, 'purpose_id', 'mode_id', 'tp']
        )['trips'].sum().reset_index()

    # ## Read in 24hr matrix ## #
    dist_fname = du.get_dist_name(
        trip_origin,
        matrix_format,
        str(year),
        str(purpose),
        str(mode),
        str(segment),
        str(car_availability),
        csv=True
    )
    pa_24hr = pd.read_csv(os.path.join(pa_import, dist_fname))
    zoning_system = pa_24hr.columns[0]

    print("Working on splitting %s..." % dist_fname)

    # Convert from wide to long format
    y_zone = 'a_zone' if model_zone == 'p_zone' else 'd_zone'
    pa_24hr = du.expand_distribution(
        pa_24hr,
        year,
        purpose,
        mode,
        segment,
        car_availability,
        id_vars=model_zone,
        var_name=y_zone,
        value_name='trips'
    )

    # ## Narrow tp_split down to just the segment here ## #
    segment_id = 'soc_id' if purpose in [1, 2] else 'ns_id'
    segmentation_mask = du.get_segmentation_mask(
        tp_split,
        col_vals={
            'purpose_id': purpose,
            'mode_id': mode,
            segment_id: str(segment),
            'car_availability_id': car_availability,
        },
        ignore_missing_cols=True
    )
    tp_split = tp_split.loc[segmentation_mask]
    tp_split = tp_split.reindex([model_zone, 'tp', 'trips'], axis=1)

    # ## Calculate the time split factors for each zone ## #
    unq_zone = tp_split[model_zone].drop_duplicates()
    for zone in unq_zone:
        zone_mask = (tp_split[model_zone] == zone)
        tp_split.loc[zone_mask, 'time_split'] = (
                tp_split[zone_mask]['trips'].values
                /
                tp_split[zone_mask]['trips'].sum()
        )
    time_splits = tp_split.reindex(
        [model_zone, 'tp', 'time_split'],
        axis=1
    )

    # ## Apply tp-split factors to total pa_24hr ## #
    unq_time = time_splits['tp'].drop_duplicates()
    for time in unq_time:
        # Need to do a left join, and set any missing vals. Ensures
        # zones don't go missing if there's an issue with tp_split input
        # NOTE: tp3 is missing for p2, m1, soc0, ca1
        time_factors = time_splits.loc[time_splits['tp'] == time]
        gb_tp = pd.merge(
            pa_24hr,
            time_factors,
            on=[model_zone],
            how='left'
        ).rename(columns={'trips': 'dt'})
        gb_tp['time_split'] = gb_tp['time_split'].fillna(0)
        gb_tp['tp'] = gb_tp['tp'].fillna(time).astype(int)

        # Calculate the number of trips for this time_period
        gb_tp['dt'] = gb_tp['dt'] * gb_tp['time_split']

        # ## Aggregate back up to our segmentation ## #
        all_seg_cols = [
            model_zone,
            y_zone,
            "purpose_id",
            "mode_id",
            "soc_id",
            "ns_id",
            "car_availability_id",
            "tp"
        ]

        # Get rid of cols we're not using
        seg_cols = [x for x in all_seg_cols if x in gb_tp.columns]
        gb_tp = gb_tp.groupby(seg_cols)["dt"].sum().reset_index()

        # Build write path
        tp_pa_name = du.get_dist_name(
            str(trip_origin),
            str(matrix_format),
            str(year),
            str(purpose),
            str(mode),
            str(segment),
            str(car_availability),
            tp=str(time)
        )
        tp_pa_fname = tp_pa_name + '.csv'
        out_tp_pa_path = os.path.join(
            pa_export,
            tp_pa_fname
        )

        # Convert table from long to wide format and save
        # TODO: Generate header based on mode used
        du.long_to_wide_out(
            gb_tp.rename(columns={model_zone: zoning_system}),
            v_heading=zoning_system,
            h_heading=y_zone,
            values='dt',
            out_path=out_tp_pa_path
        )


def efs_build_tp_pa(tp_import: str,
                    pa_import: str,
                    pa_export: str,
                    years_needed: List[int],
                    p_needed: List[int],
                    m_needed: List[int],
                    soc_needed: List[int] = None,
                    ns_needed: List[int] = None,
                    ca_needed: List[int] = None,
                    matrix_format: str = 'pa',
                    process_count: int = -2
                    ) -> None:
    """
    Converts the 24hr matrices in pa_import into time_period segmented
    matrices - outputting to pa_export

    Parameters
    ----------
    tp_import:
        Path to the dir containing the seed values to use for splitting
        pa_import matrices by tp

    pa_import:
        Path to the directory containing the 24hr matrices

    pa_export:
        Path to the directory to export the tp split matrices

    years_needed:
        A list of which years of 24hr Matrices to convert.

    p_needed:
        A list of which purposes of 24hr Matrices to convert.

    m_needed:
        A list of which modes of 24hr Matrices to convert.

    soc_needed:
        A list of which soc of 24hr Matrices to convert.

    ns_needed:
        A list of which ns of 24hr Matrices to convert.

    ca_needed:
        A list of which car availabilities of 24hr Matrices to convert.

    matrix_format:
        Which format the matrix is in. Either 'pa' or 'od'

    process_count:
        The number of processes to use when multiprocessing. Negative numbers
        use that many processes less than the max. i.e. -1 ->
        os.cpu_count() - 1

    Returns
    -------
        None

    """
    # Validate inputs
    if matrix_format not in consts.VALID_MATRIX_FORMATS:
        raise ValueError("'%s' is not a valid matrix format."
                         % str(matrix_format))

    # Init
    soc_needed = [None] if soc_needed is None else soc_needed
    ns_needed = [None] if ns_needed is None else ns_needed
    ca_needed = [None] if ca_needed is None else ca_needed

    # ## MULTIPROCESS ## #
    unchanging_kwargs = {
        'pa_import': pa_import,
        'pa_export': pa_export,
        'matrix_format': matrix_format,
        'tp_import': tp_import
    }

    # Build a list of the changing arguments
    kwargs_list = list()
    for year in years_needed:
        loop_generator = du.segmentation_loop_generator(
            p_needed,
            m_needed,
            soc_needed,
            ns_needed,
            ca_needed
        )

        for p, m, seg, ca in loop_generator:
            kwargs = unchanging_kwargs.copy()
            kwargs.update({
                'year': year,
                'purpose': p,
                'mode': m,
                'segment': seg,
                'car_availability': ca
            })
            kwargs_list.append(kwargs)

    # Multiprocess - split by time period and write to disk
    multiprocessing.multiprocess(
        _build_tp_pa_internal,
        kwargs=kwargs_list,
        process_count=process_count
    )


def _build_od_internal(pa_import,
                       od_export,
                       model_name,
                       calib_params,
                       phi_lookup_folder,
                       phi_type,
                       aggregate_to_wday,
                       full_od_out=False,
                       echo=True):
    """
    The internals of build_od(). Useful for making the code more
    readable du to the number of nested loops needed

    TODO: merge with TMS - NOTE:
    All this code below has been mostly copied from TMS pa_to_od.py
    function of the same name. A few filenames etc have been changed
    to make sure it properly works with NorMITs demand files (This is
    du to NorMITs demand needing moving in entirety over to the Y drive)

    Returns
    -------

    """
    # Init
    tps = ['tp1', 'tp2', 'tp3', 'tp4']
    matrix_totals = list()
    dir_contents = os.listdir(pa_import)
    mode = calib_params['m']
    purpose = calib_params['p']

    model_zone_col = model_name + '_zone_id'

    # Print out some info
    dist_name = du.calib_params_to_dist_name('hb', 'od', calib_params)
    print("Generating %s..." % dist_name)

    # Get appropriate phis and filter
    phi_factors = get_time_period_splits(
        mode,
        phi_type,
        aggregate_to_wday=aggregate_to_wday,
        lookup_folder=phi_lookup_folder)
    phi_factors = simplify_time_period_splits(phi_factors)
    phi_factors = phi_factors[phi_factors['purpose_from_home'] == purpose]

    # Get the relevant filenames from the dir
    dir_subset = dir_contents.copy()
    for name, param in calib_params.items():
        # Work around for 'p2' clashing with 'tp2'
        if name == 'p':
            dir_subset = [x for x in dir_subset if '_' + name + str(param) in x]
        else:
            dir_subset = [x for x in dir_subset if (name + str(param)) in x]

    # Build dict of tp names to filenames
    tp_names = {}
    for tp in tps:
        tp_names.update({tp: [x for x in dir_subset if tp in x][0]})

    # ## Build from_home dict from imported from_home PA ## #
    frh_dist = {}
    for tp, path in tp_names.items():
        dist_df = pd.read_csv(os.path.join(pa_import, path))
        zone_nums = dist_df[model_zone_col]     # Save to re-attach later
        dist_df = dist_df.drop(model_zone_col, axis=1)
        frh_dist.update({tp: dist_df})

    # ## Build to_home matrices from the from_home PA ## #
    frh_ph = {}
    for tp_frh in tps:
        du.print_w_toggle('From from_h ' + str(tp_frh), echo=echo)
        frh_int = int(tp_frh.replace('tp', ''))
        phi_frh = phi_factors[phi_factors['time_from_home'] == frh_int]

        # Transpose to flip P & A
        frh_base = frh_dist[tp_frh].copy()
        frh_base = frh_base.values.T

        toh_dists = {}
        for tp_toh in tps:
            # Get phi
            du.print_w_toggle('\tBuilding to_h ' + str(tp_toh), echo=echo)
            toh_int = int(tp_toh.replace('tp', ''))
            phi_toh = phi_frh[phi_frh['time_to_home'] == toh_int]
            phi_toh = phi_toh['direction_factor']

            # Cast phi toh
            phi_mat = np.broadcast_to(phi_toh,
                                      (len(frh_base),
                                       len(frh_base)))
            tp_toh_mat = frh_base * phi_mat
            toh_dists.update({tp_toh: tp_toh_mat})
        frh_ph.update({tp_frh: toh_dists})

    # ## Aggregate to_home matrices by time period ## #
    # removes the from_home splits
    tp1_list = list()
    tp2_list = list()
    tp3_list = list()
    tp4_list = list()
    for item, toh_dict in frh_ph.items():
        for toh_tp, toh_dat in toh_dict.items():
            if toh_tp == 'tp1':
                tp1_list.append(toh_dat)
            elif toh_tp == 'tp2':
                tp2_list.append(toh_dat)
            elif toh_tp == 'tp3':
                tp3_list.append(toh_dat)
            elif toh_tp == 'tp4':
                tp4_list.append(toh_dat)

    toh_dist = {
        'tp1': np.sum(tp1_list, axis=0),
        'tp2': np.sum(tp2_list, axis=0),
        'tp3': np.sum(tp3_list, axis=0),
        'tp4': np.sum(tp4_list, axis=0)
    }

    # ## Output the from_home and to_home matrices ## #
    for tp in tps:
        # Get output matrices
        output_name = tp_names[tp]

        output_from = frh_dist[tp]
        from_total = output_from.sum().sum()
        output_from_name = output_name.replace('pa', 'od_from')

        output_to = toh_dist[tp]
        to_total = output_to.sum().sum()
        output_to_name = output_name.replace('pa', 'od_to')

        # ## Gotta fudge the row/column names ## #
        # Add the zone_nums back on
        output_from = pd.DataFrame(output_from).reset_index()
        # noinspection PyUnboundLocalVariable
        output_from['index'] = zone_nums
        output_from.columns = [model_zone_col] + zone_nums.tolist()
        output_from = output_from.set_index(model_zone_col)

        output_to = pd.DataFrame(output_to).reset_index()
        output_to['index'] = zone_nums
        output_to.columns = [model_zone_col] + zone_nums.tolist()
        output_to = output_to.set_index(model_zone_col)

        # With columns fixed, created full OD output
        output_od = output_from + output_to
        output_od_name = output_name.replace('pa', 'od')

        du.print_w_toggle('Exporting ' + output_from_name, echo=echo)
        du.print_w_toggle('& ' + output_to_name, echo=echo)
        if full_od_out:
            du.print_w_toggle('& ' + output_od_name, echo=echo)
        du.print_w_toggle('To ' + od_export, echo=echo)

        # Output from_home, to_home and full OD matrices
        output_from_path = os.path.join(od_export, output_from_name)
        output_to_path = os.path.join(od_export, output_to_name)
        output_od_path = os.path.join(od_export, output_od_name)

        # TODO: Add tidality checks into efs_build_od()
        # Auditing checks - tidality
        # OD from = PA
        # OD to = if it leaves it should come back
        # OD = 2(PA)
        output_from.to_csv(output_from_path)
        output_to.to_csv(output_to_path)
        if full_od_out:
            output_od.to_csv(output_od_path)

        matrix_totals.append([output_name, from_total, to_total])

    return matrix_totals


def efs_build_od(pa_import: str,
                 od_export: str,
                 model_name: str,
                 p_needed: List[int],
                 m_needed: List[int],
                 soc_needed: List[int],
                 ns_needed: List[int],
                 ca_needed: List[int],
                 years_needed: List[int],
                 phi_lookup_folder: str = None,
                 phi_type: str = 'fhp_tp',
                 aggregate_to_wday: bool = True,
                 echo: bool = True,
                 process_count: int = -2
                 ) -> None:
    """
     This function imports time period split factors from a given path.
    TODO: write efs_build_od() docs

    Parameters
    ----------
    pa_import
    od_export
    model_name
    p_needed
    m_needed
    soc_needed
    ns_needed
    ca_needed
    years_needed
    phi_lookup_folder
    phi_type
    aggregate_to_wday
    echo
    process_count:
        The number of processes to use when multiprocessing. Set to 0 to not
        use multiprocessing at all. Set to -1 to use all expect 1 available
        CPU.

    Returns
    -------
    None
    """
    # Init
    if phi_lookup_folder is None:
        phi_lookup_folder = 'Y:/NorMITs Demand/import/phi_factors'

    # ## MULTIPROCESS ## #
    unchanging_kwargs = {
       'pa_import': pa_import,
       'od_export': od_export,
       'model_name': model_name,
       'phi_lookup_folder': phi_lookup_folder,
       'phi_type': phi_type,
       'aggregate_to_wday': aggregate_to_wday,
       'echo': echo
    }

    # Build a list of the changing arguments
    kwargs_list = list()
    for year in years_needed:
        loop_generator = du.cp_segmentation_loop_generator(
            p_needed,
            m_needed,
            soc_needed,
            ns_needed,
            ca_needed
        )

        for calib_params in loop_generator:
            calib_params['yr'] = year
            kwargs = unchanging_kwargs.copy()
            kwargs.update({
                'calib_params': calib_params,
            })
            kwargs_list.append(kwargs)

    # Multiprocess - split by time period and write to disk
    matrix_totals = multiprocessing.multiprocess(
        _build_od_internal,
        kwargs=kwargs_list,
        process_count=process_count,
        in_order=True
    )

    # Make sure individual process outputs are concatenated together
    return [y for x in matrix_totals for y in x]


def maybe_get_aggregated_tour_proportions(orig: int,
                                          dest: int,
                                          model_tour_props: Dict[int, Dict[int, np.array]],
                                          lad_tour_props: Dict[int, Dict[int, np.array]],
                                          tfn_tour_props: Dict[int, Dict[int, np.array]],
                                          model2lad: Dict[int, int],
                                          model2tfn: Dict[int, int],
                                          cell_demand: float,
                                          ) -> np.array:
    # Translate to the aggregated zones
    lad_orig = model2lad.get(orig, -1)
    lad_dest = model2lad.get(dest, -1)
    tfn_orig = model2tfn.get(orig, -1)
    tfn_dest = model2tfn.get(dest, -1)

    # If the model zone tour proportions are zero, fall back on the
    # aggregated tour proportions
    bad_key = False
    if not cell_demand > 0:
        # The cell demand is zero - it doesn't matter which tour props
        # we use
        od_tour_props = model_tour_props[orig][dest]

    elif model_tour_props[orig][dest].sum() != 0:
        od_tour_props = model_tour_props[orig][dest]

    elif lad_tour_props[lad_orig][lad_dest].sum() != 0:
        # First - fall back to LAD aggregation
        od_tour_props = lad_tour_props[lad_orig][lad_dest]

        # We have a problem if this used a negative key
        bad_key = lad_orig < 0 or lad_dest < 0

    elif tfn_tour_props[tfn_orig][tfn_dest].sum() != 0:
        # Second - Try fall back to TfN Sector aggregation
        od_tour_props = tfn_tour_props[tfn_orig][tfn_dest]

        # We have a problem if this used a negative key
        bad_key = tfn_orig < 0 or tfn_dest < 0

    else:
        # If all aggregations are zero, and the zone has grown
        # we probably have a problem elsewhere
        raise ValueError(
            "Could not find a non-zero tour proportions for (O, D) pair "
            "(%s, %s). This likely means there was a problem when "
            "generating these tour proportions."
            % (str(orig), str(dest))
        )

    if bad_key:
        raise KeyError(
            "A negative key was used to get aggregated tour proportions. "
            "This probably means that either the origin or destination "
            "zone could not be found in the zone translation files. Check "
            "the zone translation files for (O, D) pair (%s, %s) "
            "to make sure."
            % (str(orig), str(dest))
        )

    return od_tour_props


def to_od_via_tour_props(orig_vals,
                         dest_vals,
                         pa_24,
                         tour_props,
                         lad_tour_props,
                         tfn_tour_props,
                         zone_translate_dir,
                         tp_needed,
                         input_dist_name,
                         model_name,
                         ):
    # TODO: Write to_od_via_tour_props() docs

    # Make sure tour props are the right shape
    du.check_tour_proportions(
        tour_props=tour_props,
        n_tp=len(tp_needed),
        n_row_col=len(orig_vals)
    )

    for tp_dict in [lad_tour_props, tfn_tour_props]:
        du.check_tour_proportions(
            tour_props=tp_dict,
            n_tp=len(tp_needed),
            n_row_col=len(tp_dict)
        )

    # Load the zone aggregation dictionaries for this model
    model2lad = du.get_zone_translation(
        import_dir=zone_translate_dir,
        from_zone=model_name,
        to_zone='lad'
    )
    model2tfn = du.get_zone_translation(
        import_dir=zone_translate_dir,
        from_zone=model_name,
        to_zone='tfn_sectors'
    )

    # Create empty from_home OD matrices
    fh_mats = dict()
    for tp in tp_needed:
        fh_mats[tp] = pd.DataFrame(0.0,
                                   index=pa_24.index,
                                   columns=pa_24.columns)

    # Create empty to_home OD matrices
    th_mats = dict()
    for tp in tp_needed:
        th_mats[tp] = pd.DataFrame(0.0,
                                   index=pa_24.index,
                                   columns=pa_24.columns)

    # For each OD pair, generate value from 24hr PA & tour_prop
    # TODO: Stop all of the tqdm bars overwriting each other
    # Some info on how to do it https://github.com/tqdm/tqdm/pull/329
    total = len(orig_vals) * len(dest_vals)
    desc = "Converting %s to tp split OD..." % input_dist_name
    for orig, dest in tqdm(product(orig_vals, dest_vals), total=total, desc=desc):

        # Will get the aggregated tour props if needed
        od_tour_props = maybe_get_aggregated_tour_proportions(
            orig=orig,
            dest=dest,
            model_tour_props=tour_props,
            lad_tour_props=lad_tour_props,
            tfn_tour_props=tfn_tour_props,
            model2lad=model2lad,
            model2tfn=model2tfn,
            cell_demand=pa_24.loc[orig, dest]
        )

        # Generate the values for the from home mats
        fh_factors = np.sum(od_tour_props, axis=1)
        for i, tp in enumerate(fh_mats.keys()):
            fh_mats[tp].loc[orig, dest] = pa_24.loc[orig, dest] * fh_factors[i]

        # Generate the values for the to home mats
        th_factors = np.sum(od_tour_props, axis=0)
        for i, tp in enumerate(th_mats.keys()):
            th_mats[tp].loc[orig, dest] = pa_24.loc[orig, dest] * th_factors[i]

    return fh_mats, th_mats


def _tms_od_from_tour_props_internal(pa_import,
                                     od_export,
                                     tour_proportions_dir,
                                     zone_translate_dir,
                                     model_name,
                                     trip_origin,
                                     base_year,
                                     year,
                                     p,
                                     m,
                                     seg,
                                     ca,
                                     tp_needed
                                     ) -> None:
    # TODO: Write _tms_od_from_tour_props_internal docs()
    # Load in 24hr PA
    input_dist_name = du.get_dist_name(
        trip_origin=trip_origin,
        matrix_format='pa',
        year=str(year),
        purpose=str(p),
        mode=str(m),
        segment=str(seg),
        car_availability=str(ca),
        csv=True
    )
    pa_24 = pd.read_csv(os.path.join(pa_import, input_dist_name), index_col=0)
    pa_24.columns = pa_24.columns.astype(int)
    pa_24.index = pa_24.index.astype(int)

    # Get a list of the zone names for iterating - make sure integers
    orig_vals = [int(x) for x in pa_24.index.values]
    dest_vals = [int(x) for x in list(pa_24)]

    # ## Load the tour proportions - always generated on base year ## #
    # Load the model zone tour proportions
    tour_prop_fname = du.get_dist_name(
        trip_origin=trip_origin,
        matrix_format='tour_proportions',
        year=str(base_year),
        purpose=str(p),
        mode=str(m),
        segment=str(seg),
        car_availability=str(ca),
        suffix='.pkl'
    )
    tour_props = pd.read_pickle(os.path.join(tour_proportions_dir,
                                             tour_prop_fname))

    # Load the aggregated tour props
    lad_fname = tour_prop_fname.replace('tour_proportions', 'lad_tour_proportions')
    lad_tour_props = pd.read_pickle(os.path.join(tour_proportions_dir, lad_fname))

    tfn_fname = tour_prop_fname.replace('tour_proportions', 'tfn_tour_proportions')
    tfn_tour_props = pd.read_pickle(os.path.join(tour_proportions_dir, tfn_fname))

    fh_mats, th_mats = to_od_via_tour_props(
        orig_vals,
        dest_vals,
        pa_24,
        tour_props,
        lad_tour_props,
        tfn_tour_props,
        zone_translate_dir,
        tp_needed,
        input_dist_name,
        model_name=model_name,
    )

    print("Writing %s converted matrices to disk..." % input_dist_name)

    # Save the generated from_home matrices
    for tp, mat in fh_mats.items():
        dist_name = du.get_dist_name(
            trip_origin=trip_origin,
            matrix_format='od_from',
            year=str(year),
            purpose=str(p),
            mode=str(m),
            segment=str(seg),
            car_availability=str(ca),
            tp=str(tp),
            csv=True
        )
        mat.to_csv(os.path.join(od_export, dist_name))

    # Save the generated to_home matrices
    for tp, mat in th_mats.items():
        dist_name = du.get_dist_name(
            trip_origin=trip_origin,
            matrix_format='od_to',
            year=str(year),
            purpose=str(p),
            mode=str(m),
            segment=str(seg),
            car_availability=str(ca),
            tp=str(tp),
            csv=True
        )
        # Need to transpose to_home before writing
        mat.T.to_csv(os.path.join(od_export, dist_name))


def _tms_od_from_tour_props(pa_import: str,
                            od_export: str,
                            tour_proportions_dir: str,
                            zone_translate_dir: str,
                            model_name: str,
                            base_year: str = consts.BASE_YEAR,
                            years_needed: List[int] = consts.FUTURE_YEARS,
                            p_needed: List[int] = consts.ALL_HB_P,
                            m_needed: List[int] = consts.MODES_NEEDED,
                            soc_needed: List[int] = None,
                            ns_needed: List[int] = None,
                            ca_needed: List[int] = None,
                            tp_needed: List[int] = consts.TIME_PERIODS,
                            process_count: int = os.cpu_count() - 2
                            ) -> None:
    # TODO: Write _tms_od_from_tour_props() docs
    # Init
    soc_needed = [None] if soc_needed is None else soc_needed
    ns_needed = [None] if ns_needed is None else ns_needed
    ca_needed = [None] if ca_needed is None else ca_needed

    # Make sure all purposes are home based
    for p in p_needed:
        if p not in consts.ALL_HB_P:
            raise ValueError("Got purpose '%s' which is not a home based "
                             "purpose. generate_tour_proportions() cannot "
                             "handle nhb purposes." % str(p))
    trip_origin = 'hb'

    # MP placed inside this loop to prevent too much Memory being used
    for year in years_needed:
        loop_generator = du.segmentation_loop_generator(
            p_list=p_needed,
            m_list=m_needed,
            soc_list=soc_needed,
            ns_list=ns_needed,
            ca_list=ca_needed
        )

        # ## MULTIPROCESS ## #
        unchanging_kwargs = {
            'pa_import': pa_import,
            'od_export': od_export,
            'tour_proportions_dir': tour_proportions_dir,
            'zone_translate_dir': zone_translate_dir,
            'model_name': model_name,
            'trip_origin': trip_origin,
            'base_year': base_year,
            'year': year,
            'tp_needed': tp_needed
        }

        kwargs_list = list()
        for p, m, seg, ca in loop_generator:
            kwargs = unchanging_kwargs.copy()
            kwargs.update({
                'p': p,
                'm': m,
                'seg': seg,
                'ca': ca
            })
            kwargs_list.append(kwargs)

        multiprocessing.multiprocess(
            _tms_od_from_tour_props_internal,
            kwargs=kwargs_list,
            process_count=process_count
        )

        # Repeat loop for every wanted year


def _vdm_od_from_tour_props_internal(pa_import,
                                     od_export,
                                     tour_proportions_dir,
                                     zone_translate_dir,
                                     model_name,
                                     trip_origin,
                                     base_year,
                                     year,
                                     uc,
                                     m,
                                     ca,
                                     tp_needed
                                     ) -> None:
    # TODO: Write _vdm_od_from_tour_props_internal docs()
    # TODO: Is there a way to combine get_vdm_dist_name and get_dist_name?
    #  Cracking this would make all future code super easy flexible!
    # Load in 24hr PA
    input_dist_name = du.get_vdm_dist_name(
        trip_origin=trip_origin,
        matrix_format='pa',
        year=str(year),
        user_class=str(uc),
        mode=str(m),
        ca=ca,
        csv=True
    )
    pa_24 = pd.read_csv(os.path.join(pa_import, input_dist_name), index_col=0)
    pa_24.columns = pa_24.columns.astype(int)
    pa_24.index = pa_24.index.astype(int)

    # Get a list of the zone names for iterating - make sure integers
    orig_vals = [int(x) for x in pa_24.index.values]
    dest_vals = [int(x) for x in list(pa_24)]

    # ## Load the tour proportions - always generated on base year ## #
    # Load the model zone tour proportions
    tour_prop_fname = du.get_vdm_dist_name(
        trip_origin=trip_origin,
        matrix_format='tour_proportions',
        year=str(year),
        user_class=str(uc),
        mode=str(m),
        ca=ca,
        suffix='.pkl'
    )
    tour_props = pd.read_pickle(os.path.join(tour_proportions_dir,
                                             tour_prop_fname))

    # Load the aggregated tour props
    lad_fname = tour_prop_fname.replace('tour_proportions', 'lad_tour_proportions')
    lad_tour_props = pd.read_pickle(os.path.join(tour_proportions_dir, lad_fname))

    tfn_fname = tour_prop_fname.replace('tour_proportions', 'tfn_tour_proportions')
    tfn_tour_props = pd.read_pickle(os.path.join(tour_proportions_dir, tfn_fname))

    fh_mats, th_mats = to_od_via_tour_props(
        orig_vals,
        dest_vals,
        pa_24,
        tour_props,
        lad_tour_props,
        tfn_tour_props,
        zone_translate_dir,
        tp_needed,
        input_dist_name,
        model_name=model_name,
    )

    print("Writing %s converted matrices to disk..." % input_dist_name)

    # Save the generated from_home matrices
    for tp, mat in fh_mats.items():
        dist_name = du.get_vdm_dist_name(
            trip_origin=trip_origin,
            matrix_format='od_from',
            year=str(year),
            user_class=str(uc),
            mode=str(m),
            ca=ca,
            tp=str(tp),
            csv=True
        )
        mat.to_csv(os.path.join(od_export, dist_name))

    # Save the generated to_home matrices
    for tp, mat in th_mats.items():
        dist_name = du.get_vdm_dist_name(
            trip_origin=trip_origin,
            matrix_format='od_to',
            year=str(year),
            user_class=str(uc),
            mode=str(m),
            ca=ca,
            tp=str(tp),
            csv=True
        )
        # Need to transpose to_home before writing
        mat.T.to_csv(os.path.join(od_export, dist_name))


def _vdm_od_from_tour_props(pa_import: str,
                            od_export: str,
                            tour_proportions_dir: str,
                            zone_translate_dir: str,
                            model_name: str,
                            base_year: str = consts.BASE_YEAR,
                            years_needed: List[int] = consts.FUTURE_YEARS,
                            to_needed: List[str] = consts.VDM_TRIP_ORIGINS,
                            uc_needed: List[str] = consts.USER_CLASSES,
                            m_needed: List[int] = consts.MODES_NEEDED,
                            ca_needed: List[int] = None,
                            tp_needed: List[int] = consts.TIME_PERIODS,
                            process_count: int = os.cpu_count() - 2
                            ):
    # TODO: Write _vdm_od_from_tour_props() docs
    # Init
    ca_needed = [None] if ca_needed is None else ca_needed

    # MP placed inside this loop to prevent too much Memory being used
    for year in years_needed:
        loop_generator = du.vdm_segment_loop_generator(
            to_list=to_needed,
            uc_list=uc_needed,
            m_list=m_needed,
            ca_list=ca_needed
        )

        # ## MULTIPROCESS ## #
        unchanging_kwargs = {
            'pa_import': pa_import,
            'od_export': od_export,
            'tour_proportions_dir': tour_proportions_dir,
            'zone_translate_dir': zone_translate_dir,
            'model_name': model_name,
            'base_year': base_year,
            'year': year,
            'tp_needed': tp_needed
        }

        kwargs_list = list()
        for to, uc, m, ca in loop_generator:
            kwargs = unchanging_kwargs.copy()
            kwargs.update({
                'trip_origin': to,
                'uc': uc,
                'm': m,
                'ca': ca
            })
            kwargs_list.append(kwargs)

        multiprocessing.multiprocess(
            _vdm_od_from_tour_props_internal,
            kwargs=kwargs_list,
            process_count=process_count
        )

        # Repeat loop for every wanted year


def build_od_from_tour_proportions(pa_import: str,
                                   od_export: str,
                                   tour_proportions_dir: str,
                                   zone_translate_dir: str,
                                   model_name: str,
                                   seg_level: str,
                                   seg_params: Dict[str, Any],
                                   base_year: str = consts.BASE_YEAR,
                                   years_needed: List[int] = consts.FUTURE_YEARS,
                                   process_count: int = os.cpu_count() - 2
                                   ) -> None:
    """
    Builds future year OD matrices based on the base year tour proportions
    at tour_proportions_dir.

    Parameters
    ----------
    pa_import:
        Path to the directory containing the 24hr matrices.

    od_export:
        Path to the directory to export the future year tp split OD matrices.

    tour_proportions_dir:
        Path to the directory containing the base year tour proportions.

    zone_translate_dir:
        Where to find the zone translation files from the model zoning system
        to the aggregated LAD nad TfN zoning systems.

    base_year:
        The base year that the tour proportions were generated for

    years_needed:
        The future year matrices that need to be converted from PA to OD

    p_needed:
        A list of purposes to use when converting from PA to OD

    m_needed:
        A list of modes to use when converting from PA to OD

    soc_needed:
        A list of skill levels to use when converting from PA to OD

    ns_needed:
        A list of income levels to use when converting from PA to OD

    ca_needed:
        A list of car availabilities to use when converting from PA to OD

    tp_needed:
        A list of time periods to use when converting from PA to OD

    process_count:
        The number of processes to use when multiprocessing. Set to 0 to not
        use multiprocessing at all. Set to -1 to use all expect 1 available
        CPU.

    Returns
    -------
    None
    """
    # TODO: Update build_od_from_tour_proportions() docs
    # Init
    seg_level = du.validate_seg_level(seg_level)

    # Call the correct mid-level function to deal with the segmentation
    if seg_level == 'tms':
        to_od_fn = _tms_od_from_tour_props
    elif seg_level == 'vdm':
        to_od_fn = _vdm_od_from_tour_props
    else:
        raise NotImplementedError(
            "'%s' is a valid segmentation level, however, we do not have a "
            "mid-level function to deal with it at the moment."
            % seg_level
        )

    to_od_fn(
        pa_import=pa_import,
        od_export=od_export,
        tour_proportions_dir=tour_proportions_dir,
        zone_translate_dir=zone_translate_dir,
        model_name=model_name,
        base_year=base_year,
        years_needed=years_needed,
        process_count=process_count,
        **seg_params
    )