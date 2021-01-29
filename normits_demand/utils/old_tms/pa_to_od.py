# -*- coding: utf-8 -*-
"""
Created on Wed Mar  4 11:40:10 2020

@author: cruella
"""
import os
import warnings

import pandas as pd
import numpy as np # Here we go

# import matrix_processing as mp

from normits_demand.utils import general as nup


_default_lookup_folder = 'Y:/NorMITs Synthesiser/import/phi_factors'

_default_file_drive = 'Y:/'
_default_model_name = 'Norms'
_default_iteration = 'iter99'

"""
def init(movements, # TBC
         distribution_segments,
         init_params,
         o_paths):

    # BUILD INTERNAL 24HR PA BY MODE
    # get all zone movements for OD conversion
    # TODO: movements should be passed
    all_zone_movements = movements.copy()
    # Edit zone names
    all_zone_movements = all_zone_movements.rename(
                    columns={list(all_zone_movements)[0]:'o_zone',
                             list(all_zone_movements)[1]:'d_zone'})

    # TODO: Set defaults for mode split paths here, not globally

    # Fairly tricky bit of code below to deal with segments
    # Copy the dist segments and remove mode and purpose
    # TODO: pass distribution segments
    unq_seg = distribution_segments.copy()
    unq_seg.remove('purpose')
    unq_seg.remove('mode')

    return(None)
"""

def path_config(file_drive,
                model_name,
                iteration,
                internal_input,
                external_input):
    
    
    """
    Sets paths for imports to be set as variables.
    Creates project folders.

    Parameters
    ----------
    file_drive = 'Y:/':
        Name of root drive to do work on. Defaults to TfN Y drive.

    model_name:
        Name of model as string. Should be same as model descriptions.

    iteration:
        Current iteration of model. Defaults to global default.

    Returns
    ----------
    [0] imports:
        Paths to all Synthesiser import parameters.

    [1] exports:
        Paths to all Synthesiser output parameters
    """

    # Set base dir
    home_path = os.path.join(file_drive, 'NorMITs Synthesiser')

    # Set synth import folder
    import_path = os.path.join(home_path, 'import')

    # Set top level model folder, leave the slash on
    model_path = os.path.join(home_path,
                              model_name,
                              iteration)
    model_path += os.path.sep

    # Set model lookups location
    model_lookup_path = os.path.join(home_path,
                                     model_name,
                                     'Model Zone Lookups')

    # Set production path, leave slash on
    production_path = os.path.join(model_path, 'Production Outputs')
    production_path += os.path.sep

    # Set production path
    production_path = (model_path +
                       'Production Outputs/')

    p_import_path = (production_path +
                     'hb_productions_' +
                     model_name.lower() +
                     '.csv')

    # Raise user warning if no productions by this name
    if not os.path.exists(p_import_path):
        warnings.warn('No productions in folder.' +
                      'Check path or run production model')

    # Create project folders
    distribution_path = os.path.join(model_path, 'Distribution Outputs')
    nup.create_folder(distribution_path, chDir=False)

    fusion_path = os.path.join(model_path, 'Fusion Outputs')
    nup.create_folder(fusion_path, chDir=False)

    summary_matrix_import = os.path.join(distribution_path, '24hr PA Distributions')

    external_import = os.path.join(distribution_path,
                                   'External Distributions')

    synth_pa_export = os.path.join(distribution_path, 'PA Matrices')
    nup.create_folder(synth_pa_export, chDir=False)

    synth_pa_export_24 = os.path.join(distribution_path, 'PA Matrices 24hr')
    nup.create_folder(synth_pa_export_24, chDir=False)

    synth_od_export = os.path.join(distribution_path, 'OD Matrices')
    nup.create_folder(synth_od_export, chDir=False)

    # Set fusion exports
    fusion_summary_import = os.path.join(fusion_path, '24hr Fusion PA Distributions')

    fusion_pa_export = os.path.join(fusion_path, 'Fusion PA Matrices')
    nup.create_folder(fusion_pa_export, chDir=False)

    fusion_pa_export_24 = os.path.join(fusion_path, 'Fusion PA Matrices 24hr')
    nup.create_folder(fusion_pa_export_24, chDir=False)

    fusion_od_export = os.path.join(fusion_path, 'Fusion OD Matrices')
    nup.create_folder(fusion_od_export, chDir=False)

    if internal_input == 'synthetic':
        internal_import = summary_matrix_import
        print('Picking up from synthetic internal')
        pa_export = synth_pa_export
        pa_export_24 = synth_pa_export_24
        od_export = synth_od_export
    elif internal_input == 'fusion':
        internal_import = fusion_summary_import
        print('Picking up from fusion internal')
        pa_export = fusion_pa_export
        pa_export_24 = fusion_pa_export_24
        od_export = fusion_od_export

    # Compile into import and export
    imports = {'imports': import_path,
               'lookups': model_lookup_path,
               'production_import': p_import_path,
               'internal': internal_import,
               'external': external_import,
               'pa': pa_export,
               'pa_24': pa_export_24}

    exports = {'pa': pa_export,
               'pa_24': pa_export_24,
               'od':od_export}

    return imports, exports

# TODO: Ensure runs work for all models with all segmentations
# TODO: Fully separate tp pa and pa to od functionality.
# TODO: Object layer
# TODO: All writes as square format - for speed

def build_tp_pa(file_drive = _default_file_drive,
                model_name = _default_model_name,
                iteration = _default_iteration,
                distribution_segments = ['p', 'm'],
                internal_input = 'synthetic',
                external_input = 'synthetic',
                write_modes = [1,2,3,5,6],
                arrivals = False,
                export_24hr = False,
                arrival_export = None,
                write = True):

    """
    internal_input = 'fusion' or 'synthetic'
    external_input = 'fusion' or 'synthetic'
    """
    
    #
    paths = path_config(file_drive,
                        model_name,
                        iteration,
                        internal_input,
                        external_input)
    i_paths = paths[0]
    o_paths = paths[1]

    # Get init params
    init_params = nup.get_init_params(i_paths['lookups'],
                                      distribution_type='hb',
                                      model_name=model_name,
                                      mode_subset=write_modes,
                                      purpose_subset=None)

    # Get productions
    productions = pd.read_csv(i_paths['production_import'])
    model_zone = [x for x in list(productions) if model_name.lower() in x][0]

    unq_purpose = init_params['p'].drop_duplicates(
            ).reset_index(drop=True)

    # Set import folders
    internal_dir = os.listdir(i_paths['internal'])
    internal_dir = [x for x in internal_dir if 'nhb' not in x]
    external_dir = os.listdir(i_paths['external'])
    external_dir = [x for x in external_dir if 'nhb' not in x]

    # Set export folders
    if arrivals:
        arrivals_path = arrival_export

    tp_pa_builds = init_params.index

    tp_pa_path = (o_paths['pa'] +
                  '/hb_pa')

    matrix_totals = []
    for tp_pa in tp_pa_builds:
        print(tp_pa)
        calib_params = {}
        compile_params = {}
        for ds in distribution_segments:
            calib_params.update({ds:init_params[ds][tp_pa]})
            print(calib_params)

        p_subset = productions.copy()
            # Subset productions
        for index,cp in calib_params.items():
            if cp != 'none':
                p_subset = p_subset[p_subset[index]==cp]

        # Work out time split
        # This won't work if there are duplicates
        p_totals = p_subset.reindex(
                [model_zone, 'trips'], axis=1).groupby(
                        model_zone).sum().reset_index()
        p_totals = p_totals.rename(columns={'trips':'p_totals'})
        tp_totals = p_subset.reindex(
                [model_zone,
                 'tp',
                 'trips'], axis=1).groupby(
                 [model_zone, 'tp']).sum().reset_index()
        time_splits = tp_totals.merge(p_totals,
                                      how='left',
                                      on=[model_zone])
        time_splits['time_split'] = (time_splits['trips']/
                   time_splits['p_totals'])
        time_splits = time_splits.drop(['p_totals'], axis=1)

        # Import internal & externals
        int_seg_import = internal_dir.copy()
        ext_seg_import = external_dir.copy()
        # Do internal & external at the same time because clever
        for index,cp in calib_params.items():
            if cp != 'none':
                int_seg_import = [x for x in int_seg_import if (
                        index + str(cp)) in x]
                ext_seg_import = [x for x in ext_seg_import if (
                        index + str(cp)) in x]

        # test len internal
        if len(int_seg_import) > 1:
            print('Duplicate import segment warning')
            print(int_seg_import)
            int_seg_import = int_seg_import[0]
        elif len(int_seg_import) == 0:
            print(int_seg_import)
            raise ValueError('No segment to import')
        else:
            int_seg_import = int_seg_import[0]

        # test len external
        if len(ext_seg_import) > 1:
            print('Duplicate export segment warning')
            print(ext_seg_import)
            ext_seg_import = int_seg_import[0]
        elif len(ext_seg_import) == 0:
            print(ext_seg_import)
            raise ValueError('No segment to import')
        else:
            ext_seg_import = ext_seg_import[0]

        # TODO: Make all of this the same
        internal = pd.read_csv(i_paths['internal'] + '/' + int_seg_import)
        if list(internal)[0] == model_zone:
            internal = internal.drop(model_zone, axis=1)
        elif list(internal)[0] == 'o_zone':
            internal = internal.drop('o_zone', axis=1)
        elif list(internal)[0] == 'Unnamed: 0':
            internal = internal.drop('Unnamed: 0', axis=1)
        external = pd.read_csv(i_paths['external'] + '/' + ext_seg_import)
        if list(external)[0] == model_zone:
            external = external.drop(model_zone, axis=1)
        elif list(external)[0] == 'o_zone':
            external = external.drop('o_zone', axis=1)
        elif list(external)[0] == 'Unnamed: 0':
            external = external.drop('Unnamed: 0', axis=1)
        # external = external.drop(list(external)[0],axis=1)

        internal = internal.values
        i_ph = np.zeros([len(external), len(external)])
        i_ph[0:len(internal),0:len(internal)] = internal
        internal = i_ph.copy()

        external = external.values

        gb = internal + external
        
        # Export 24hr here if required.
        if export_24hr:
            if write:
                write_path_24 = nup.build_path(tp_pa_path,
                                               calib_params)
                
                if calib_params['m'] in write_modes:
                    all_zone_ph = pd.DataFrame(
                            {model_zone:[
                                    i for i in np.arange(1, len(external)+1)]})
                    all_zone_ph['ph'] = 1

                    gb_24 = pd.DataFrame(gb,
                                         index=all_zone_ph[model_zone],
                                         columns=all_zone_ph[
                                                 model_zone]).reset_index()

                    gb_24.to_csv(write_path_24,
                                 index=False)

        # Apply time period - if not 24hr - see loop above
        else:
            unq_time = time_splits['tp'].drop_duplicates()
            
            for time in unq_time:
                print('tp' + str(time))
                time_ph = time_splits.copy()
                time_ph = time_ph[time_ph['tp']==time].reset_index(drop=True)
                time_ph = time_ph.drop('tp', axis=1)

                compile_params.update(
                        {'base_productions':time_ph['trips'].sum()})

                all_zone_ph = pd.DataFrame(
                        {model_zone:[
                                i for i in np.arange(1, len(external)+1)]})
                all_zone_ph['ph'] = 1
                time_ph = all_zone_ph.merge(time_ph,
                                            how='left',
                                            on=[model_zone])
                time_ph['time_split'] = time_ph['time_split'].fillna(0)
                time_factors = time_ph['time_split'].values

                time_factors = np.broadcast_to(time_factors,
                                               (len(time_factors),
                                                len(time_factors))).T

                gb_tp = gb * time_factors
                compile_params.update({'gb_tp':gb_tp.sum()})    

                if arrivals:
                    arrivals_np = gb_tp.sum(axis=0)
                    arrivals_mat = pd.DataFrame(all_zone_ph[model_zone])
                    arrivals_mat['arrivals'] = arrivals_np
                
                    arrivals_write_path = nup.build_path(arrivals_path,
                                                         calib_params,
                                                         tp=time)

                # Build write paths
                tp_write_path = nup.build_path(tp_pa_path,
                                               calib_params,
                                               tp=time)
                print(tp_write_path)

                compile_params.update({'export_path':tp_write_path})

                if write:
                    # Define write path
                    if calib_params['m'] in write_modes:

                        gb_tp = pd.DataFrame(gb_tp,
                                             index=all_zone_ph[model_zone],
                                             columns=all_zone_ph[
                                                     model_zone]).reset_index()

                        gb_tp.to_csv(tp_write_path,
                                     index=False)
                
                    if arrivals:
                        # Write arrivals anyway
                        arrivals_mat.to_csv(arrivals_write_path,
                                            index=False)

                matrix_totals.append(compile_params)
                # End

    return(matrix_totals)

def build_od(file_drive = _default_file_drive,
             model_name = _default_model_name,
             iteration = _default_iteration,
             distribution_segments = ['p', 'm'],
             internal_input = 'synthetic',
             external_input = 'synthetic',
             phi_type = 'fhp_tp',
             export_modes = None,
             write = True):

    """
    Get the contents of PA output folder and translate to OD.
    Output to output folder

    """
    paths = path_config(file_drive,
                        model_name,
                        iteration,
                        internal_input,
                        external_input)
    i_paths = paths[0]
    o_paths = paths[1]

    # Get init params
    init_params = nup.get_init_params(i_paths['lookups'],
                                      distribution_type='hb',
                                      model_name=model_name,
                                      mode_subset=export_modes,
                                      purpose_subset=None)

    dir_contents = os.listdir(i_paths['pa'])

    export_subset = init_params.copy()
    export_subset = export_subset[export_subset['m'].isin(export_modes)]

    matrix_totals = []
    # Going to have to go by init params
    for index, row in export_subset.iterrows():
        print(index, row)
        calib_params = {}
        for ds in distribution_segments:
            if row[ds] != 'none':
                calib_params.update({ds:row[ds]})
        
        mode = calib_params['m']
        
        # Get purpose subset
        purpose = calib_params['p']

        # Get appropriate phis
        phi_factors = get_time_period_splits(mode,
                                             phi_type,
                                             aggregate_to_wday = True,
                                             lookup_folder = _default_lookup_folder)
        
        # Filter phis
        phi_factors = phi_factors[phi_factors['purpose_from_home']==purpose]
        
        dir_subset = dir_contents.copy()

        for name, param in calib_params.items():
            print(name, param)
            # Work around for 'p2' clashing with 'tp2'
            if name == 'p':
                dir_subset = [
                        x for x in dir_subset if (
                                '_' + name + str(param)) in x]
            else:
                dir_subset = [
                        x for x in dir_subset if (
                                name + str(param)) in x]

        tps = ['tp1','tp2','tp3','tp4']

        # Build names
        # Can do this with the list above.
        tp_names = {}
        for tp in tps:
            tp_names.update({tp:[x for x in dir_subset if tp in x][0]})

        # Import from home (PA), build dictionary
        frh_dist = {}
        for tp, path in tp_names.items():
            frh_dist.update({tp:pd.read_csv(i_paths['pa'] + '/' + path).drop(
                    (model_name.lower() + '_zone_id'),
                    axis=1)})

        # To build each toh matrix
        frh_ph = {}
        for tp_frh in tps:
            print('From frh ' + str(tp_frh))
            frh_int = int(tp_frh.replace('tp',''))
            phi_frh = phi_factors[phi_factors['time_from_home']==frh_int]
            
            frh_base = frh_dist[tp_frh].copy()
            # Transpose to flip P & A
            frh_base = frh_base.values.T

            toh_dists = {}
            for tp_toh in tps:
                # Get phi
                print('Building ' + str(tp_toh))
                toh_int = int(tp_toh.replace('tp',''))
                phi_toh = phi_frh[phi_frh['time_to_home']==toh_int]
                phi_toh = phi_toh['direction_factor']

                # Cast phi toh
                phi_mat = np.broadcast_to(phi_toh,
                                          (len(frh_base),
                                           len(frh_base)))
                tp_toh_mat = frh_base * phi_mat
                toh_dists.update({tp_toh:tp_toh_mat})
            frh_ph.update({tp_frh:toh_dists})

        # Go back over frh_ph and aggregate time period
        tp1_list = []
        tp2_list = []
        tp3_list = []
        tp4_list = []

        for item, toh_dict in frh_ph.items():
            print('From home ' + item)
            for toh_tp, toh_dat in toh_dict.items():
                print(toh_tp)
                if toh_tp == 'tp1':
                    tp1_list.append(toh_dat)
                elif toh_tp == 'tp2':
                    tp2_list.append(toh_dat)
                elif toh_tp == 'tp3':
                    tp3_list.append(toh_dat)
                elif toh_tp == 'tp4':
                    tp4_list.append(toh_dat)
        
        toh_dist = {}
        toh_dist.update({'tp1':np.sum(tp1_list, axis=0)})
        toh_dist.update({'tp2':np.sum(tp2_list, axis=0)})
        toh_dist.update({'tp3':np.sum(tp3_list, axis=0)})
        toh_dist.update({'tp4':np.sum(tp4_list, axis=0)})

        for tp in tps:
            output_from = frh_dist[tp]
            from_total = output_from.sum().sum()

            output_name = tp_names[tp]
            output_from_name = output_name.replace(
                    'pa','od_from')
           
            output_to = toh_dist[tp]
            to_total = output_to.sum().sum()

            output_to_name = output_name.replace(
                    'pa', 'od_to')
            
            # Add the indices back on
            # TODO: Should use import params
            output_from = pd.DataFrame(output_from).reset_index()
            output_from['index'] = output_from['index']+1
            output_from = output_from.rename(columns={
                    'index':(model_name.lower() + '_zone_id')})
    
            output_to = pd.DataFrame(output_to).reset_index()
            output_to['index'] = output_to['index'] + 1
            # Have to manually rename the columns here too.
            # TODO: Find where this is introduced and fix
            ph_headings = output_to['index']
            left_headings = ['index']
            for heading in ph_headings:
                left_headings.append(heading)

            output_to.columns = left_headings

            output_to = output_to.rename(columns={
                    'index':(model_name.lower() + '_zone_id')})
    
            print('Exporting ' + output_from_name)
            print('& ' + output_to_name)
            print('To ' + o_paths['od'])
            
            matrix_totals.append([output_name, from_total, to_total])
            
            output_from.to_csv((o_paths['od'] + '/' + output_from_name), index=False)
            output_to.to_csv((o_paths['od'] + '/' + output_to_name), index=False)

    return(matrix_totals)

def build_tp_pa_and_od(distribution_segments,
                       model_name,
                       internal_24hr_productions,
                       external_pa,
                       init_params, # init params
                       i_paths,
                       o_paths,
                       production_splits,
                       all_zone_movements,
                       phi_type = 'fhp_tp',
                       export_modes = None,
                       fusion_only = False,
                       fusion_modes = None, # List
                       write_tp_pa = True,
                       write_arrivals = True
                       ):

    """
    Function to replace the compile and export loop.

    Takes:
        Everything
    
    phi_type:
        Takes one of ['fhp_tp', 'fhp_24hr' 'p_tp']. From home purpose & time period
        or from home and to home purpose & time period

    """
    unq_purpose = init_params['p'].drop_duplicates(
            ).reset_index(drop=True)

    if 12 in unq_purpose.values:
        nhb = True
        print('NHB run')
    else:
        nhb = False
        print('HB run')

    unq_seg = distribution_segments.copy()
    unq_seg.remove('p')
    unq_seg.remove('m')

    # Fusion handling
    if fusion_modes is not None:
        if fusion_only:
            # TODO: This is a bit dangerous in terms of overwriting stuff
            init_params = init_params[init_params['mode'].isin(fusion_modes)].reset_index(drop=True)
            init_params['source'] = 'moira_fusion'
            # Set export folders
            pa_export = o_paths['fusion_pa_export']
            od_export = o_paths['fusion_od_export']
        else:
            ValueError('Fusion modes provided but Fusion only not specified')
    else:
        # Set export folders
        pa_export = o_paths['pa']
        od_export = o_paths['od_export']
        if fusion_only:
            ValueError('Please specify fusion modes, or toggle fusion only to False')

    # Define handling for segments
    if len(list(unq_seg)) > 0:
        unq_seg = init_params.reindex(
                unq_seg,
                axis=1).drop_duplicates().reset_index(drop=True)
    else:
        a = {'null_seg': ['']}
        unq_seg = pd.DataFrame(a)

    # Use row.index, where index is col no to get segment names
    for index, row in unq_seg.iterrows():
        print(row)

        # Filter out betas to segs
        try:
            seg_betas = init_params[
                    init_params[
                            row.index[0]]==row[0]].reset_index(drop=True)
        except:
            # If fail, there's no segments
            print('No segments, passing init params')
            # Copy betas straight across
            seg_betas = init_params.copy()
            # No seg subset required from 24hr productions
            seg_subset = internal_24hr_productions.copy()

        else:
            print('Subsetting segment ' + str(row.index[0]))
            # Filter internal 24 to segs.
            seg_subset = internal_24hr_productions.copy()
            seg_betas = init_params.copy()
            # Build total productions placeolder, to avoid double counting across segments
            
            ## TODO: Difference between text and int causing havoc here
            for seg in unq_seg:
                print('Filtering input paths to: ' +
                      seg + ' = ' + str(row[seg]))
                # Build beta subset
                seg_betas = seg_betas[
                        seg_betas[seg]==row[seg]]
                seg_betas = seg_betas.reset_index(drop=True)

            for seg in unq_seg:
                if row[seg] != 'none':
                    print('Filtering input productions to: ' +
                          seg + ' = ' + str(row[seg]))
                    # Build production subset
                    seg_subset = seg_subset[seg_subset[seg]==int(row[
                                            seg])]
                    seg_subset = seg_subset.reset_index(drop=True)

        # Define unq mode for mode subset GB tp pa
        unq_mode = init_params['m'].drop_duplicates().reset_index(drop=True)

        for mode_subset in unq_mode:
            print('Reapplying time period for mode ' + str(mode_subset))
            # Get time period splits for OD conversion
            # TODO: Add mode differentiation    
            time_period_splits = get_time_period_splits(mode = mode_subset,
                                                        phi_type = phi_type,
                                                        aggregate_to_wday = True)

            # if 'purpose_to_home' in these columns, you have to do the tp allocation with it
            if 'purpose_to_home' in list(time_period_splits):
                to_home_phi = True
            else:
                to_home_phi = False
            print('To home phi: ' + str(to_home_phi))

            print(mode_subset)
            # Reimport full set of betas
            mode_betas = seg_betas[
                    seg_betas[
                            'm']==mode_subset].reset_index(drop=True)

            # So far takes 'cjtw', 'synthetic', 'moira_fusion'
            # TODO: This is pretty handy now but need to optimise output
            reimport_dict = {}
            reimport_dict.update({'synthetic':o_paths['summaries']})
            if not nhb:
                reimport_dict.update({'cjtw':o_paths['cjtw']})
            reimport_dict.update({'moira_fusion':o_paths['fusion_summaries']})

            # Filter internal_24hr_productions to mode only
            dist_subset = seg_subset[
                    seg_subset[
                            'm']==mode_subset].reset_index(drop=True)

            # Should never balance if there are fusion modes
            if fusion_modes is not None:
                balance = False
            else:
                balance = True

            # Create full matrix from re-imports
            internal_pa = compile_internal_pa(reimport_dict,
                                              mode_betas, # init_params
                                              (model_name.lower() + '_zone_id'), # ia_name
                                              dist_subset, # internal_24hr_productions
                                              distribution_segments, # distribution_segments
                                              current_segment = row, # current_segment
                                              balance = balance,
                                              nhb = nhb)

            # Resum segments in case any duplication
            ipa_cols = ['p_zone', 'a_zone']
            for ds in distribution_segments:
                ipa_cols.append(ds)

            internal_pa = internal_pa.groupby(
                    ipa_cols).sum().reset_index()

            # TODO: production report or trip length audit call

            # REAPPLY TIME PERIOD SPLITS TO GET TIME PERIOD PA

            # Some segments don't have a full set of purposes
            # redefine here
            s_unq_purpose = internal_pa['p'].drop_duplicates(
                    ).reset_index(drop=True)

            # Define purpose list
            for purpose in s_unq_purpose:
                print('Compiling purpose ' +
                      str(purpose) +
                      ' at time period PA')

                # Can name the full export now
                export_name = ('_m' +
                               str(mode_subset) +
                               '_p' +
                               str(purpose))

                # External to Internal PA
                subset_external_pa = external_pa[
                        external_pa['m']==mode_subset].copy()
                subset_external_pa = subset_external_pa[
                        subset_external_pa ['p'] == purpose]

                # Flexible segment detection and filter for externals
                if row.index[0] != 'null_seg':
                    for seg_heading in list(unq_seg):
                        print(seg_heading)
                        print(row[seg_heading])

                        # Append to export name
                        export_name += ('_' + seg_heading)
                        export_name += (str(row[seg_heading]))

                        # Filter externals
                        if row[seg_heading] != 'none':
                            subset_external_pa = subset_external_pa[
                                    subset_external_pa[seg_heading] == int(row[seg_heading])]

                subset_internal_pa = internal_pa[
                        internal_pa['m']==mode_subset]
                subset_internal_pa = subset_internal_pa[
                        subset_internal_pa['p'] == purpose]

                subset_pa = pd.concat([subset_internal_pa,
                                       subset_external_pa], sort=True).reset_index(drop=True)

                # Get subset total for comparison
                s_pa_t = subset_pa['dt'].sum()
                print(s_pa_t)

                # Add model name to resplit 24hr
                # TODO: This is where the segment split loop should start - avoid directly handling unsplit
                subset_tp_pa = resplit_24hr_pa(i_paths['lookups'],
                                               (model_name.lower() + '_zone_id'),
                                               subset_pa,
                                               # Default - does this need to be GB or Int only?
                                               splits = production_splits,
                                               mode_subset = mode_subset,
                                               purpose_subset = [purpose],
                                               aggregation_segments = distribution_segments)

                # Comparison total
                s_pa_tp_t = subset_tp_pa['dt'].sum()

                print('Total before: ' + str(s_pa_t))
                print('Total after: ' + str(s_pa_tp_t))

                # TODO: Can delete subset_pa now?
                del(subset_pa)

                # Reindex tp_pa for mode purpose and time only
                # Can drop mode now, if there's only ever one
                # Define path to write out
                # TODO: Define earlier
                if nhb:
                    trip_origin = 'nhb'
                else:
                    trip_origin = 'hb'
                
                # Define export path, export tp pa by mode
                subset_tp_pa_path = (pa_export +
                                     '/' + trip_origin +
                                     '_tp_pa_' +
                                     export_name +
                                     '.csv')

                if (write_tp_pa) and (mode_subset in export_modes):
                    print('')
                    subset_tp_pa.to_csv(subset_tp_pa_path,
                                        index=False)

                # Split to OD
                # You can't do them in one go.
                # TODO: End of function before this line!!
                if nhb == True:
                    subset_tp_od = subset_tp_pa.copy()
                    
                    subset_tp_od = subset_tp_od.rename(columns={'p_zone':'o_zone',
                                                                'a_zone':'d_zone'})
    
                    for tp in subset_tp_od['time'].drop_duplicates(
                            ).reset_index(drop=True):
                        print(tp)
                        mat = subset_tp_od[
                                subset_tp_od[
                                        'time']==tp].reset_index(drop=True)

                        del(mat['time'])
                        mat = mp.matrix_long_to_wide(mat,
                                                     all_zone_movements,
                                                     merge_cols = ['o_zone',
                                                                   'd_zone'])
                        od_nhb_path = (od_export +
                                       '/nhb_od_tp' +
                                       str(tp) +
                                       '_' +
                                       export_name +
                                       '.csv')

                        if mode_subset in export_modes:
                            print('Exporting NHB for mode: ' + str(mode_subset))
                            mat.to_csv(od_nhb_path)   

                if nhb == False:
                    subset_tp_od = tp_pa_to_od(subset_tp_pa,
                                               time_period_splits = time_period_splits)

                    # Split from
                    subset_tp_od_from = subset_tp_od[0].reindex(
                            ['o_zone', 'd_zone',
                             'time', 'dt'],
                             axis=1).groupby(
                                     ['o_zone', 'd_zone',
                                      'time']).sum().reset_index()

                    for tp in subset_tp_od_from['time'].drop_duplicates(
                            ).reset_index(drop=True):
                        print(tp)
                        mat = subset_tp_od_from[
                                subset_tp_od_from[
                                        'time']==tp].reset_index(drop=True)

                        del(mat['time'])
                        mat = mp.matrix_long_to_wide(mat,
                                                     all_zone_movements,
                                                     merge_cols = ['o_zone',
                                                                   'd_zone'])

                        # Export matrix format OD - leave index on!
                        od_from_path = (
                                        od_export +
                                        '/hb_od_tp' +
                                        str(tp) +
                                        '_' +
                                        export_name +
                                        '_from.csv')
        
                        if mode_subset in export_modes:
                            mat.to_csv(od_from_path)

                    # Split to
                    subset_tp_od_to = subset_tp_od[1].reindex(
                            ['o_zone', 'd_zone',
                             'time', 'dt'], axis=1).groupby(
                             ['o_zone', 'd_zone', 'time']).sum().reset_index()

                    for tp in subset_tp_od_to['time'].drop_duplicates().reset_index(drop=True):
                        print(tp)
                        mat = subset_tp_od_to[subset_tp_od_to['time']==tp].reset_index(drop=True)

                        del(mat['time'])
                        mat = mp.matrix_long_to_wide(mat,
                                                     all_zone_movements,
                                                     merge_cols = ['o_zone',
                                                                   'd_zone'])

                        od_to_path = (od_export +
                                      '/hb_od_tp' +
                                      str(tp) +
                                      '_' +
                                      export_name +
                                      '_to.csv')
                        if mode_subset in export_modes:
                            mat.to_csv(od_to_path)

                    # Export arrivals
                    if fusion_only == False:
                        arrivals = subset_tp_od[2]

                        arrivals_path = (o_paths['arrival_export'] +
                                         '/hb_' +
                                         export_name +
                                         '_arrivals.csv')

                        if write_arrivals:
                            arrivals.to_csv(arrivals_path, index=False)
                        # End of HB OD

    return(True)

def compile_internal_pa(reimport_dict,
                        mode_betas,
                        ia_name,
                        dist_subset,
                        distribution_segments,
                        current_segment = None,
                        balance = False,
                        nhb = False):
    """
    This function takes a dictionary containing a pair of name to folder name,
    iterates over the items in the dictionary and imports the relevant
    distributed matrices based on the betas passed to the function.
    Then, it compiles them into a single distributed dataframe for a full model
    area based on import parameters contained in the initial betas parameter
    table.

    Parameters
    ----------
    reimport_dict:
        Target folder. Will work for any folder containing csvs.

    init_params:
        Betas.

    ia_name:
        Name of internal area of model.

    internal_24hr_productions:
        Trips for internal area aggregated to 24hr.

    distribution_segments:
        List of column headings describing current segmentation. For grouping.

    current_segments = None:
        Current segment parameters for reimport. Needs to be a row or df.

    balance = True:
        Adjust reimported productions back up to target productions or not.

    Returns
    ----------
    matrix_list:
        Compiled csvs.
    """
    # TODO fix balance for NHB
    
    # Build copy of dist subset
    dist_s = dist_subset.copy()

    if not nhb:
        dist_s = dist_s.rename(
                columns={ia_name:'p_zone'})

    # Build columns to group and join by below
    group_cols = ['p_zone', 'a_zone']
    for ds in distribution_segments:
        group_cols.append(ds)

    index_cols = group_cols.copy()
    index_cols.append('dt')

    # Need to to this to get productions only
    group_cols.remove('a_zone')

    print(group_cols)
    print(index_cols)

    # Reimport
    hb_pa = []
    for name,path in reimport_dict.items():
        print(name)
        print(path)
        # Define mode and purposes required from this reimport
        mode_purpose = mode_betas[mode_betas['source']==name]
        #
        segment_lists = []

        # Handle segments
        # Very very tricky
        if current_segment.index[0] == 'null_seg':
            print('No segments')
        else:
            for segment in current_segment.index:
                print(segment)
                ph_segment = mode_purpose[segment].drop_duplicates(
                        ).reset_index(drop=True)
                segment_lists.append(ph_segment)

        mode_list = mode_purpose['m'].drop_duplicates(
                ).reset_index(drop=True)

        purpose_list = mode_purpose['p'].drop_duplicates(
                ).reset_index(drop=True)

        if name == 'cjtw':
            cjtw_sub = mode_list.copy()
            mode_list = None

        # Needs to be forced to import cjtw for p1 if there are segments
        matrix = import_loop(import_folder = path,
                             mode_list = mode_list,
                             purpose_list = purpose_list,
                             segment_lists = segment_lists)

        if matrix is not None:

            # If it's cjtw then filter the matrix to the mode list
            # for single mode builds
            # This used to be outside the matrix loop call
            # TODO: more filtering?
            if name == 'cjtw':
                matrix = matrix[matrix['m'].isin(
                        cjtw_sub)].reset_index(drop=True)
                if current_segment.index[0] == 'null_seg':
                    for segment in segment_lists:
                        print(segment.name)
                        matrix = matrix[
                                matrix[segment.name] == current_segment[
                                        segment.name]]

            print(list(matrix))
            hb_pa.append(matrix)

    hb_pa = pd.concat(hb_pa, sort=True)

    # if balance:
    #     hb_pa_totals = hb_pa.drop('a_zone',axis=1).groupby(
    #             group_cols).sum().reset_index()
    #     hb_pa_totals = hb_pa_totals.merge(internal_24hr_productions,
    #                                       how='left',
    #                                       on = group_cols)
    #     hb_pa_totals['growth'] = hb_pa_totals['trips'] / hb_pa_totals['dt']
    #     hb_pa_totals = hb_pa_totals.drop(['dt', 'trips'],axis=1)
    #     hb_pa = hb_pa.merge(hb_pa_totals,
    #                         how='left',
    #                         on=group_cols)
    #     hb_pa['dt'] = hb_pa['dt'] * hb_pa['growth']
    #    hb_pa = hb_pa.drop(['growth'],axis=1)

    hb_pa = hb_pa.reindex(index_cols,axis=1).sort_values(index_cols).reset_index(drop=True)

    return(hb_pa)

def import_loop(import_folder,
                mode_list = None,
                purpose_list = None,
                segment_lists = None):
    """
    This function imports every csv from an import folder and appends them to a
    single DataFrame. Filters out distributions based on mode list and purpose
    list passed to function. The code is madness, frankly but it works, sometimes.

    Parameters
    ----------
    import_folder:
        Target folder. Will work for any folder containing csvs.

    Returns
    ----------
    matrix_list:
        Compiled csvs.
    """
    target_dir = os.listdir(import_folder)
    if 'cjtw_purpose_1.csv' in target_dir:
        cjtw = True
    else:
        cjtw = False

    # Turn other segments into something we can check outputs for
    if cjtw == False:
        if segment_lists is not None:
            lookup_segment_list = []
            for segment in segment_lists:
                seg_ph = []
                for seg in segment:
                    if seg != 'none':
                        seg_ph.append(segment.name + '_' + str(seg))
                        seg_ph.append(segment.name + str(seg))
                        lookup_segment_list.append(seg_ph)
                del(seg_ph)
    elif cjtw == True:
        segment_lists = None

    # Turn mode list into something we can check outputs for
    if mode_list is not None:
        lookup_mode_list = []
        for mode in mode_list:
            lookup_mode_list.append('m_' + str(mode))
            lookup_mode_list.append('m' + str(mode))

    # Turn purpose list into something we can check outputs for
    if purpose_list is not None:
        lookup_purpose_list = []
        for purpose in purpose_list:
            lookup_purpose_list.append('p_' + str(purpose))
            lookup_purpose_list.append('p' + str(purpose))
    # Filter out omitted segments:
    if segment_lists is not None:
        segments_for_import = []
        for s_list in lookup_segment_list:
            ph_segment = []
            for segment in s_list:
                ph_segment.append([x for x in target_dir if segment in x])
            segments_for_import.append(ph_segment)
            del(ph_segment)
        for segment in segments_for_import:
            print(segment)
            segment = [inner for outer in segment for inner in outer]
    else:
        segments_for_import = target_dir

    # Filter out omitted modes
    if mode_list is not None:
        m_for_import = []
        for mode in lookup_mode_list:
            m_for_import.append([x for x in target_dir if mode in x])
        m_for_import = [inner for outer in m_for_import for inner in outer]
    else:
        m_for_import = target_dir

    # Filter out omitted purposes
    if purpose_list is not None:
        p_for_import = []
        for purpose in lookup_purpose_list:
            p_for_import.append([x for x in target_dir if purpose in x])
        p_for_import = [inner for outer in p_for_import for inner in outer]
    else:
        p_for_import = target_dir

    # Go back to target dir and filter out all omitted modes and purposes
    import_list = []
    for import_path in target_dir:
        if import_path in m_for_import and import_path in p_for_import:
            # If there are segments for import, append based on them
            if len(segments_for_import) > 0:
                # Brutal workaround for ignoring cjtw
                if cjtw == False:
                    for segment in segments_for_import:
                        if any(import_path in s for s in segment):
                            import_list.append(import_path)
                elif cjtw == True:
                    import_list.append(import_path)
            # Otherwise append above segment
            else:
                import_list.append(import_path)

    # Hard exception for census journey to work
    # Makes it import twice now.
    # TODO: Function needs to be looked at
    # if cjtw:
    #    import_list.append(target_dir[0])
    #    print(import_list)
    #    print('Cjtw run found')

    matrix_list = []
    for matrix in import_list:
        # Import matrices and append to list
        print('Re-importing ' + matrix)
        ph = pd.read_csv(import_folder +
                         '/' +
                         matrix)

        matrix_list.append(ph)
        del(ph)

    # Concatenate the imports, if they're there
    try:
        matrix_list = pd.concat(matrix_list)
        return(matrix_list)
    except ValueError:
        print('Nothing in', import_folder)
        return(None)

def tp_pa_to_od(mainland_gb_pa,
                time_period_splits = None):

    # TODO: Check if this will run with A non-mainland matrix
    """
    This function takes a mainland gb pa matrix and splits the trips out into
    O-D format. It also counts the arrivals

    Parameters
    ----------
    mainland_gb_pa:
        Matrix of mainland GB productions split by time and mode.

    time_period_splits:
        A dataframe of factors for splitting out 'from' trips to 'to' trips.

    Returns
    ----------
    [0] od_from:
        Origin half of PA matrix, from home legs.

    [1] od_to:
        Destination half of PA matrix, to home legs.

    [2] arrivals:
        Origin grouped od_to, retains split time period for NHB.
    """
    # Factor down to reduce segments

    # Get total 'before' productions
    total_pa_productions = mainland_gb_pa['dt'].sum()
    print(total_pa_productions)

    od_from = mainland_gb_pa.copy()
    del(mainland_gb_pa)
    # TODO: Remove divide by 2
    od_from['dt'] = od_from['dt'].values
    od_from = od_from.rename(columns={'p_zone':'o_zone',
                                      'a_zone':'d_zone'})

    # Get total 'from' productions, should be half total above
    total_od_from_productions = od_from['dt'].sum()
    print('total od from productions ' + str(total_od_from_productions))

    # Rename columns in time_period_splits for
    time_period_splits = time_period_splits.rename(
            columns={'purpose_from_home':'purpose',
                     'time_from_home':'time'})

    # Covert to OD
    print('merging time splits')
    od_to = od_from.copy()

    # Possibly the culprit
    # Flip O-D
    od_to = od_to.rename(columns={'o_zone':'new_d_zone',
                                  'd_zone':'new_o_zone'})
    od_to = od_to.rename(columns={'new_d_zone':'d_zone',
                                  'new_o_zone':'o_zone'})

    # Get uniq purpose
    unq_purpose = od_to['purpose'].drop_duplicates().reset_index(drop=True)

    od_bin = []
    for pp in unq_purpose:
        print('Appending to purpose ' + str(pp))

        to_sub = od_to[od_to['purpose']==pp]
        to_sub = to_sub.merge(time_period_splits,
                              how = 'inner',
                              on = ['purpose','time'])

        del(to_sub['purpose'], to_sub['time'])
        to_sub = to_sub.rename(
                columns={'purpose_to_home':'purpose',
                         'time_to_home':'time'})

        to_sub['dt'] = (to_sub['dt'].values *
             to_sub['direction_factor'].values)
        del(to_sub['direction_factor'])

        # Regroup
        to_sub = to_sub.groupby(
                ['o_zone', 'd_zone', 'purpose',
                 'mode','time']).sum().reset_index()

        od_bin.append(to_sub)
        # End of loop

    od_to = pd.concat(od_bin, sort=True)
    del(od_bin)
    od_to = od_to.reindex(list(od_from),axis=1).reset_index(drop=True)

    total_od_to_productions = od_from['dt'].sum()
    print('total od to productions' + str(total_od_to_productions))

    od_from = nup.optimise_data_types(od_from)
    od_to = nup.optimise_data_types(od_to)

    arrival_cols = ['o_zone', 'purpose', 'mode', 'time', 'dt']
    arrivals = od_to.reindex(arrival_cols, axis=1).groupby(
            ['o_zone', 'purpose', 'mode', 'time']).sum().reset_index()

    return(od_from, od_to, arrivals)

def resplit_24hr_pa(model_lookup_path,
                    ia_name,
                    internal_pa,
                    splits = None,
                    mode_subset = None,
                    purpose_subset = None,
                    aggregation_cols = None):
    """
    This function takes a distributed 24hr PA matrix, imports the production
    splits from the relevant model folder, rejoins them and multiplies the
    distributed trips back out by the splitting factors.
    The subset depends on the splits given. If it goes to default it will do
    it for internal only.
    This is the crucial function in the model as it defines output splits
    and presents the largest memory bottleneck.

    Parameters
    ----------
    model_lookup_path:
        PA matrix for a given distribution.

    ia_name:
         Dataframe row containing target parameters for mode and purpose.

    internal_pa:
        I don't actually know! Can I add a mainland GB by mode here?

    aggregation_cols:
        Columns to aggregate by for aggregation exports. Includes core of
        ['p_zone', 'a_zone', 'mode', 'purpose'] by default. Time is non-core
        and will need to be specified.

    Returns
    ----------
    internal_pa:
        PA Matrix with time period splits added back in.
    """
    # TODO: Fix temporary fix here - whole thing should be import only.
    # TODO: very tempted to use mode constrained splits
     
    if splits is None:
        # Import internal splits splits
        splits = pd.read_csv(model_lookup_path + '/production_splits.csv')

    # Rename to generic column for join
    splits = splits.rename(columns={ia_name:'p_zone'})

    # Get pre re-split total
    pre_split_total = sum(internal_pa['dt'])

    # Filter on mode - takes int not list, assumes we only ever want 1 mode
    # Otherwise this will need to be as a list
    if mode_subset is not None:
        internal_pa = internal_pa[internal_pa['m']==mode_subset]

    if purpose_subset is not None:
        internal_pa = internal_pa[internal_pa['p'].isin(purpose_subset)]

    # Chunk join for memory efficiency
    unq_purpose_mode = internal_pa.reindex(
            ['p', 'm'],axis=1).drop_duplicates(
                    ).reset_index(drop=True)

    merge_placeholder = []

    for index,row in unq_purpose_mode.iterrows():
        print(row)
        ph_dat = internal_pa[internal_pa['p']==row['p']]
        ph_dat = ph_dat[ph_dat['m']==row['m']]
        print('subset before re-split: ' + str(ph_dat['dt'].sum()))

        merge_cols = ['m', 'p']

        ph_dat = ph_dat.merge(splits,
                              how='inner',
                              on=['p_zone',
                                  'm',
                                  'p'])

        # Re-split trip rates
        ph_dat['dt'] = (ph_dat['dt'].values *
              ph_dat['tp'].values)

        print('subset after re-split: ' + str(ph_dat['dt'].sum()))

        # Loop to subset by given model categories for PA level writes
        # Needed for Norms output print_audits (Norms does its own PA-OD conversion)

        # Define core aggregations
        format_list = ['p_zone',
                       'a_zone']

        # append any aggregation cols
        if aggregation_cols is not None:

            for agg in aggregation_cols:
                format_list.append(agg)

        format_list_dt = format_list.copy()
        format_list_dt.append('dt')
        print(format_list_dt)
        ph_dat = ph_dat.reindex(format_list_dt,
                                 axis=1).groupby(
                                         format_list).sum().reset_index()

        print('subset after aggregation: ' + str(ph_dat['dt'].sum()))

        print(list(ph_dat))
        # Optimise data types
        # ph_dat = nup.optimise_data_types(ph_dat)

        merge_placeholder.append(ph_dat)
        del(ph_dat)

    # Concatenate df
    internal_pa = pd.concat(
            merge_placeholder,
            sort=False)
    del(merge_placeholder)

    # Reset index
    internal_pa = internal_pa.reset_index(
            drop=True)

    # Print audit
    print('total before re-split: ' + str(pre_split_total))
    print('after re-split: ' + str(sum(internal_pa['dt'])))

    return(internal_pa)

def get_time_period_splits(mode = None,
                           phi_type = None,
                           aggregate_to_wday = True,
                           lookup_folder = _default_lookup_folder):
    """
    This function imports time period split factors from a given path.

    Parameters
    ----------
    mode:
        Target mode as single integer

    phi_type:
        Takes one of ['fhp_tp', 'fhp_24hr' 'p_tp']. From home purpose & time period
        or from home and to home purpose & time period

    aggregate_to_wday:
        Boolean to aggregate to weekday or not.

    Returns:
    ----------
    period_time_splits:
        DataFrame containing time split factors for pa to od.
    """
    # List folder contents
    folder_contents = os.listdir(lookup_folder)
    
    # Subset contents on target mode
    folder_contents = [x for x in folder_contents if ('mode' + '_' + str(mode)) in x]

    # Subset contents on target phi type
    folder_contents = [x for x in folder_contents if phi_type in x]

    # Warn if returning more than one result
    if len(folder_contents) > 1:
        print('Still two phi sets to choose from: ')
        print(folder_contents)
        print('Defaulting to the first' + folder_contents[0])

    elif len(folder_contents) == 0:
        print('No dedicated phis')
        folder_contents = ['IphiHDHD_Final.csv']
        print('Defaulting to CTripEnd params ' + folder_contents[0])

    # Import period time splits
    period_time_splits = pd.read_csv(lookup_folder + '/' + folder_contents[0])

    # Audit new totals
    if aggregate_to_wday:
        # TODO: This could be a lot easier

        # Define target times
        target_times = [1,2,3,4]

        # Filter time from home to target
        period_time_splits = period_time_splits[
                period_time_splits[
                        'time_from_home'].isin(target_times)]
        period_time_splits = period_time_splits[
                period_time_splits[
                        'time_to_home'].isin(target_times)]

        # Different methods depending on the phi type
        # If it's to home purpose only, split on from home col only
        unq_combo = period_time_splits.reindex(
                ['purpose_from_home'], axis=1).drop_duplicates(
                        ).reset_index(drop=True)

        # Define period time split placeholder
        pts_ph = []

        # Loop to do the factor
        for c_index, combo in unq_combo.iterrows():    
            purpose_frame = period_time_splits.copy()
            for param in combo.index:
                # Subset down
                purpose_frame = purpose_frame[
                        purpose_frame[param] == combo[param]]

            # Get unq times from home
            unq_tfh = purpose_frame[
                    'time_from_home'].drop_duplicates(
                    ).reset_index(drop=True)

            # Placeholder for consolidated time
            ctph = []
            # Loop to get new factors
            for tfh in unq_tfh:
                time_sub = purpose_frame.copy()
                time_sub = time_sub[
                        time_sub[
                                'time_from_home']==tfh]
                time_sub = time_sub[
                        time_sub['time_to_home'].isin(target_times)]
                
                new_total = time_sub['direction_factor'].sum()
                
                time_sub['direction_factor'] = time_sub[
                        'direction_factor']/new_total
                
                ctph.append(time_sub)

            purpose_frame = pd.concat(ctph, sort=True)
            pts_ph.append(purpose_frame)
        
        # Compile
        period_time_splits = pd.concat(pts_ph, sort=True)

    # Audit new totals
    from_cols = ['purpose_from_home', 'time_from_home', 'direction_factor']
    wday_from_totals = period_time_splits.reindex(from_cols,axis=1)
    from_cols.remove('direction_factor')
    wday_from_totals = wday_from_totals.groupby(
            from_cols).sum().reset_index()

    wday_totals = wday_from_totals['direction_factor'].drop_duplicates()
    for v in wday_totals.tolist():
        if not v > 0.999:
            raise ValueError('From-To split factors. A value of less than 1 '
                             'was returned, indicating the conversion has '
                             'dropped trips. Value returned: %f' % v)

    return(period_time_splits)


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