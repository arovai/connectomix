#!/usr/bin/env python3
"""BIDS app to compute connectomes from fmri data preprocessed with FMRIPrep

Author: Antonin Rovai

Created: August 2022
"""

# TODO list:
# - add more unittests functions
# - create more test datasets for group-level analysis, in particular featuring:
        # --- Independent samples testing DONE
        # --- Paired samples testing: inter-session OR inter-task OR inter-run comparison
        # --- Regression: covariate and confounds removal
# - include plot of null distribution of max stat in report
# - roi-to-voxel analyzes
# - cluster-based inference (mass or size)

# Restructure the config file as follows:
    # method: seed-based or roi-to-roi or ICA or ReHo or ...

import os
import argparse
import json
import yaml
import pandas as pd
import numpy as np
import nibabel as nib
import shutil
import warnings
from nibabel import Nifti1Image
from nilearn.image import load_img, resample_img, resample_to_img, clean_img, index_img, math_img, binarize_img
from nilearn.plotting import plot_matrix, plot_connectome, find_parcellation_cut_coords, find_probabilistic_atlas_cut_coords, plot_stat_map, plot_glass_brain, plot_design_matrix
from nilearn.input_data import NiftiLabelsMasker, NiftiSpheresMasker
from nilearn.connectome import ConnectivityMeasure, sym_matrix_to_vec, vec_to_sym_matrix
from nilearn.decomposition import CanICA
from nilearn.masking import apply_mask, unmask
from nilearn.regions import RegionExtractor
from nilearn.glm import threshold_stats_img
from nilearn.glm.first_level import FirstLevelModel, make_first_level_design_matrix
from nilearn.glm.second_level import SecondLevelModel, non_parametric_inference, make_second_level_design_matrix
from nilearn import datasets
from bids import BIDSLayout
import csv
from pathlib import Path
import matplotlib.pyplot as plt
from scipy.stats import ttest_ind, ttest_rel, permutation_test
from statsmodels.stats.multitest import multipletests
from statsmodels.regression.linear_model import OLS
from statsmodels.tools.tools import add_constant
from datetime import datetime

# Define the version number
__version__ = "dev"

# Set warnings to appear only once
warnings.simplefilter("once")

# TOOLS
def setup_layout(bids_dir, output_dir, derivatives=dict()):
    # Create derivative directory        
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create the dataset_description.json file
    create_dataset_description(output_dir)

    # Create a BIDSLayout to parse the BIDS dataset and index also the derivatives
    return BIDSLayout(bids_dir, derivatives=[*list(derivatives.values()), output_dir])

def setup_config(layout, config, level):
    config = load_config(config)
    
    # Set unspecified config options to default values
    if level == "participant":
        config = set_unspecified_participant_level_options_to_default(config, layout)
    elif level == "group":
        config = set_unspecified_group_level_options_to_default(config, layout)
    
    # Get the current date and time
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save a copy of the config file to the config directory
    config_filename = Path(layout.derivatives["connectomix"].root) / "config" / "backups" / f"participant_level_config_{timestamp}.json"
    save_copy_of_config(config, config_filename)
    print(f"Configuration file saved to {config_filename}")
    return config

def get_mask(layout, entities):
    entites_for_mask = entities.copy()
    entites_for_mask["desc"] = "brain"
    entites_for_mask["suffix"] = "mask"
    mask_img = layout.derivatives["fMRIPrep"].get(**entites_for_mask)
    if len(mask_img) == 1:
        mask_img = mask_img[0]
    elif len(mask_img) == 0:
        print(entites_for_mask)
        raise ValueError(f"Mask img for entities {entities} not found.")
    else:
        raise ValueError(f"More that one mask for entitites {entities} found: {mask_img}.")
    return mask_img

def get_bids_entities_from_config(config):
    """
    Extract BIDS entities from config file.

    Parameters
    ----------
    config : dict

    Returns
    -------
    dict
        Fields: subject, task, run, session and space. Each field may be str- or list of str- valued

    """
    subject = config.get("subject")
    task = config.get("tasks")
    run = config.get("runs")
    session = config.get("sessions")
    space = config.get("spaces")   
    return dict(subject=subject, task=task, run=run, session=session, space=space)

def get_files_for_analysis(layout, config):
    """
    Get functional, json and confound files from layout.derivatives,
    according to parameters in config.

    Parameters
    ----------
    layout : BIDSLayout
    config : dict

    Returns
    -------
    func_files : list
    json_files : list
    confound_files : list
    """
    # Get subjects, task, session, run and space from config file
    
    entities = get_bids_entities_from_config(config)
    
    # Select the functional, confound and metadata files
    func_files = layout.derivatives["fMRIPost-AROMA" if config["ica_aroma"] else "fMRIPrep"].get(
        suffix="bold",
        extension="nii.gz",
        return_type="filename",
        desc="nonaggrDenoised" if config["ica_aroma"] else "preproc",
        **entities
    )
    json_files = layout.derivatives["fMRIPrep"].get(
       suffix="bold",
        extension="json",
        return_type="filename",
        desc="preproc",
        **entities
    )
    
    entities.pop("space")
    confound_files = layout.derivatives["fMRIPrep"].get(
        suffix="timeseries",
        extension="tsv",
        return_type="filename",
        **entities
    )
    
    # TODO: add warning when some requested subjects don't have matching func files
    if not func_files:
        raise FileNotFoundError("No functional files found")
    if not confound_files:
        raise FileNotFoundError("No confound files found")
    if len(func_files) != len(confound_files):
        raise ValueError(f"Mismatched number of files: func_files {len(func_files)} and confound_files {len(confound_files)}")
    if len(func_files) != len(json_files):
        raise ValueError(f"Mismatched number of files: func_files {len(func_files)} and json_files {len(json_files)}")
        
    return func_files, json_files, confound_files

def setup_and_check_connectivity_kinds(config):
    # Set up connectivity measures
    connectivity_kinds = config["connectivity_kinds"]
    if isinstance(connectivity_kinds, str):
        connectivity_kinds = [connectivity_kinds]
    elif not isinstance(connectivity_kinds, list):
        raise ValueError(f"The connectivity_kinds value must either be a string or a list. You provided {connectivity_kinds}.")
    return connectivity_kinds

# Custom non-valid entity filter
def apply_nonbids_filter(entity, value, files):
    """
    Filter paths according to any type of entity, even if not allowed by BIDS.

    Parameters
    ----------
    entity : str
        The name of the entity to filter on (can be anything).
    value : str
        Entity value to filter.
    files : list
        List of paths to filters.

    Returns
    -------
    filtered_files : list
        List of paths after filtering is applied.

    """
    filtered_files = []
    if not entity == "suffix":
        entity = f"{entity}-"
    for file in files:
        if f"{entity}{value}" in os.path.basename(file).split("_"):
            filtered_files.append(file)
    return filtered_files


# Function to compare affines of images, with some tolerance
def check_affines_match(imgs):
    """
    Check if the affines of a list of Niimg objects (or file paths to .nii or .nii.gz) match.

    Parameters:
    - imgs: list of niimgs or paths

    Returns:
    - True if all affines match, False otherwise.
    """
    reference_img = nib.load(imgs[0]) if isinstance(imgs[0], (str, Path)) else imgs[0]
    reference_affine = reference_img.affine

    for img in imgs[1:]:
        img = nib.load(img) if isinstance(img, (str, Path)) else img
        if not np.allclose(img.affine, reference_affine):
            return False
    return True


# Group size verification tool
def check_group_has_several_members(group_subjects):
    """
    A basic tool to check if provided group of subjects actually contain more than one element.

    Parameters
    ----------
    group_subjects : list
        List of subjects.

    Raises
    ------
    ValueError
        Wrong size for the group list.

    Returns
    -------
    None.

    """
    if len(group_subjects) == 0:
        raise ValueError("One group has no member, please review your configuration file.")
    elif len(group_subjects) == 1:
        raise ValueError("Detecting a group with only one member, this is not yet supported. If this is not what you intended to do, review your configuration file.")


# Try to guess groups in the dataset
def guess_groups(layout):
    """
    Reads the participants.tsv file, checks for a "group" column, and returns lists of participants for each group.
    
    Parameters:
    - layout
    
    Returns:
    - groups_dict: A dictionary with group names as keys and lists of participant IDs as values.
    
    Raises:
    - Warning: If there are not exactly two groups.
    """
    
    # Path to the participants.tsv file
    participants_file = Path(layout.get(extension="tsv", scope="raw", return_type="filename")[0])
    
    # Read the participants.tsv file
    participants_df = pd.read_csv(participants_file, sep="\t")
    
    groups_dict = {}
    
    # Check if the "group" column exists
    if "group" in participants_df.columns:
        # Create lists of participants for each group
        groups_dict = {}
        unique_groups = participants_df["group"].unique()
        
        # We also need the list of participants that have been processed at participant-level
        processed_participants = layout.derivatives["connectomix"].get_subjects()
        
        for group_value in unique_groups:
            # Get the list of participant IDs for the current group
            participants_in_group = participants_df.loc[participants_df["group"] == group_value, 'participant_id'].tolist()
            
            # Remove the 'sub-' prefix:
            participants_in_group = [subject.replace('sub-', '') for subject in participants_in_group]
            
            # Refine selection to keep only participants already processed at participant-level
            groups_dict[group_value] = list(set(processed_participants) & set(participants_in_group))
        # Raise a warning if there are not exactly two groups
        if len(groups_dict) != 2:
            warnings.warn(f"Expected exactly two groups, but found {len(groups_dict)} groups.")
    else:
        warnings.warn("No group column ground in the participants.tsv file, cannot guess any grouping.")
        
    return groups_dict


# Tool to parse the various derivatives passed to CLI
def parse_derivatives(derivatives_list):
    """Convert list of 'key=value' items into a dictionary."""
    derivatives_dict = {}
    if derivatives_list:
        for item in derivatives_list:
            if '=' in item:
                key, value = item.split('=', 1)
                derivatives_dict[key] = value
            else:
                raise argparse.ArgumentTypeError(f"Invalid format for -d/--derivatives: '{item}' must be in 'key=value' format.")
    return derivatives_dict


# Tool to remove the entity defining the pairs to compare
def remove_pair_making_entity(entities):
    """
    When performing paired tests, only one type of entity can be a list with 2 values (those are used to form pairs).
    This is the "pair making entity". This function sets this entity to None.

    Parameters
    ----------
    entities : dict
        Entities to be used to form pairs in paired test.

    Returns
    -------
    unique_entities : dict
        Same as entities, with one entity set to None if it was a list of length > 1 in the input.

    """
    # Note that this function has no effect on entities in the case of independent samples comparison or during regression analysis
    unique_entities = entities.copy()
    
    task = entities['task']
    run = entities['run']
    session = entities['session']
    
    if isinstance(task, list):
        if len(task) > 1:
            unique_entities['task'] = None
    if isinstance(run, list):
        if len(run) > 1:
            unique_entities['run'] = None
    if isinstance(session, list):
        if len(session) > 1:
            unique_entities['session'] = None
        
    return unique_entities


def convert_4D_to_3D(imgs):
    """
    Convert list of 4D (or 3D) images into list of 3D images, when the fourth dimension contains only one image.

    Parameters
    ----------
    imgs : list
        List of Niimg or str of Path

    Returns
    -------
    imgs_3D : list
    """
    imgs_3D = []
    for img in imgs:
        img = nib.load(img) if isinstance(img, (str, Path)) else img
        if len(img.shape) == 4:
            if img.shape[3] == 1:
                imgs_3D.append(index_img(img, 0))
            else:
                raise ValueError("More that one image in fourth dimension, cannot convert 4D image to 3D")
    return imgs_3D


# LOADERS
# Helper function to fetch atlas maps, labels and coords
def get_atlas_data(atlas_name, get_cut_coords=False):
    """
    A wrapper function for nilearn.datasets atlas-fetching tools.

    Parameters
    ----------
    atlas_name : str
        Name of the atlas to fetch. Choose from 'schaeffer100', 'aal' or 'harvardoxford'.
    get_cut_coords : bool, optional
        If true, cut coords for the regions of the atlas will be computed. The default is False, as this is typically time-consuming.

    Returns
    -------
    maps : Nifti1Image
        The atlas maps.
    labels : list of strings.
        Labels of the atlas regions.
    coords : list of list of three integers
        The coordinates of the regions, in the same order as 'labels'.

    """
            
    if atlas_name == "schaeffer100":
        warnings.warn("Using Schaefer 2018 atlas with 100 rois")
        atlas = datasets.fetch_atlas_schaefer_2018(n_rois=100)
        maps = atlas["maps"]
        coords = find_parcellation_cut_coords(labels_img=maps) if get_cut_coords else []
        labels = atlas["labels"]
    elif atlas_name == "aal":
        warnings.warn("Using AAL atlas")
        atlas = datasets.fetch_atlas_aal()
        maps = atlas["maps"]
        coords = find_parcellation_cut_coords(labels_img=atlas['maps']) if get_cut_coords else []
        labels = atlas["labels"]
    elif atlas_name == "harvardoxford":
        warnings.warn("Using Harvard-Oxford atlas (cort-maxprob-thr25-1mm)")
        atlas = datasets.fetch_atlas_harvard_oxford("cort-maxprob-thr25-1mm")
        maps = atlas["maps"]
        coords = find_parcellation_cut_coords(labels_img=atlas['maps']) if get_cut_coords else []
        labels = atlas["labels"]
        labels=labels[1:] # Needed as first entry is 'background'
    else:
        raise ValueError(f"Requested atlas {atlas_name} is not supported. Check spelling or documentation.")
    return maps, labels, coords


# Helper function to read the repetition time (TR) from a JSON file
def get_repetition_time(json_file):
    """
    Extract repetition time from BOLD sidecar json file.

    Parameters
    ----------
    json_file : str or Path
        Path to BOLD sidecar file.

    Returns
    -------
    float
        Repetition time, in seconds.

    """
    with open(json_file, 'r') as f:
        metadata = json.load(f)
    return metadata.get('RepetitionTime', None)


# Helper function to collect participant-level matrices
def retrieve_connectivity_matrices_from_particpant_level(subjects, layout, entities, method):
    """
    Tool to retrieve the paths to the connectivity matices computed at participant-level.

    Parameters
    ----------
    subjects : list
        List of participant ID to consider.
    layout : BIDSLayout
        The usual BIDS class for the dataset.
    entities : dict
        Entities used to filter BIDSLayout.get() call.
    method : str
        Name of method to select the appropriate files.

    Raises
    ------
    FileNotFoundError
        No connectivity matrix is found, probably an error in the entities.
    ValueError
        Too many connectivity matrices are found, probably an error in the entities.

    Returns
    -------
    group_dict : dict
        A dictionary with keys = subjects and values = path to the unique connectivity matrix to the subject.

    """
    group_dict = {}
    for subject in subjects:
        conn_files = layout.derivatives["connectomix"].get(subject=subject,
                                                           suffix="matrix",
                                                           **entities,
                                                           return_type='filename',
                                                           invalid_filters='allow',
                                                           extension='.npy')
        # Refine selection with non-BIDS entity filtering
        conn_files = apply_nonbids_filter("method", method, conn_files)
        if len(conn_files) == 0:
            raise FileNotFoundError(f"Connectivity matrix for subject {subject} not found, are you sure you ran the participant-level pipeline?")
        elif len(conn_files) == 1:
            group_dict[subject] = np.load(conn_files[0])  # Load the match
        else:
            raise ValueError(f"There are multiple matches for subject {subject}, review your configuration. Matches are {conn_files}")
    return group_dict

def get_maps_from_participant_level(subjects, layout, entities, method):
    """
    Tool to retrieve the paths to the effect maps computed at participant-level (this is for the roiToVoxel method)

    Parameters
    ----------
    subjects : list
        List of participant ID to consider.
    layout : BIDSLayout
        The usual BIDS class for the dataset.
    entities : dict
        Entities used to filter BIDSLayout.get() call.
    method : str
        Name of method to select the appropriate files.

    Raises
    ------
    FileNotFoundError
        No map is found, probably an error in the entities.
    ValueError
        Too many maps are found, probably an error in the entities.

    Returns
    -------
    group_dict : dict
        A dictionary with keys = subjects and values = path to the unique effect map to the subject.

    """
    group_dict = {}
    
    local_entities = entities.copy()
    
    if 'seed' in local_entities.keys():
        seed = local_entities['seed']
        local_entities.pop('seed')
    else:
        seed = None
        
    if 'desc' in local_entities.keys():
        local_entities.pop('desc')

    for subject in subjects:
        map_files = layout.derivatives["connectomix"].get(subject=subject,
                                                           suffix="effectSize",
                                                           **local_entities,
                                                           return_type='filename',
                                                           invalid_filters='allow',
                                                           extension='.nii.gz')
        # Refine selection with non-BIDS entity filtering
        map_files = apply_nonbids_filter("method", method, map_files)
        map_files = map_files if seed is None else apply_nonbids_filter("seed", seed, map_files)
        if len(map_files) == 0:
            raise FileNotFoundError(f"Maps for subject {subject} not found, are you sure you ran the participant-level pipeline?")
        elif len(map_files) == 1:
            group_dict[subject] = map_files[0]
        else:
            raise ValueError(f"There are multiple matches for subject {subject}, review your configuration. Matches are {map_files}")
    return group_dict

# Fucntion to get participant-level data for paired analysis
def retrieve_connectivity_matrices_for_paired_samples(layout, entities, config):
    """
    returns: A dict with key equal to each subject and whose value is a length-2 list with the loaded connectivity matrices
    """
    subjects =  config["subjects"]
    
    # Extract sample-defining entities - some manual operation is required here as BIDSLayout uses singular words (e.g. 'run' unstead of 'runs')
    sample1_entities = entities.copy()
    sample1_entities['task'] = config["sample1_entities"]['tasks']
    sample1_entities['session'] = config["sample1_entities"]['sessions']
    sample1_entities['run'] = config["sample1_entities"]['runs']
    
    sample2_entities = entities.copy()
    sample2_entities['task'] = config["sample2_entities"]['tasks']
    sample2_entities['session'] = config["sample2_entities"]['sessions']
    sample2_entities['run'] = config["sample2_entities"]['runs']
    
    method = config["method"]
    
    sample1_dict = retrieve_connectivity_matrices_from_particpant_level(subjects, layout, sample1_entities, method)
    sample2_dict = retrieve_connectivity_matrices_from_particpant_level(subjects, layout, sample2_entities, method)
    
    # Let's make a consistency check, just to make sure we have what we think we have
    # This is probably not necessary though
    for subject in sample1_dict.keys():
        if subject not in sample2_dict.keys():
            raise KeyError(f"Second sample does not contain requested subject {subject}, something is wrong. Maybe a bug?")
    for subject in sample2_dict.keys():
        if subject not in sample1_dict.keys():
            raise KeyError(f"First sample does not contain requested subject {subject}, something is wrong. Maybe a bug?")
    
    # Unify the data in one dict
    paired_samples = {}
    for subject in subjects:
        paired_samples[subject] = [sample1_dict[subject], sample2_dict[subject]]
    
    return paired_samples


# Tool to extract covariate and confounds from participants.tsv in the same order as in given subject list
def retrieve_info_from_participant_table(layout, subjects, covariate, confounds=None):
    """
    Tool to extract data of interest from the participants.tsv file of the dataset.

    Parameters
    ----------
    layout : BIDSLayout
        Usual BIDS class for the dataset.
    subjects : list
        Subjects for which the data must be extracted.
    covariate : str
        Column name of participants.tsv which is to be extracted.
    confounds : list, optional
        List of strings, each of which corresponding to a column name of participants.tsv, and to be loaded as confounds. The default is None.

    Raises
    ------
    ValueError
        Name of covariate or confound does not exist in the columns of participants.tsv.

    Returns
    -------
    DataFrame
        Table to specified subjects and covariate value, optionally also with selected confounds.

    """
    # Load participants.tsv
    participants_file = layout.get(return_type='filename', extension='tsv', scope='raw')[0]
    participants_df = pd.read_csv(participants_file, sep='\t')
    
    # Ensure the measure exists in participants.tsv
    if covariate not in participants_df.columns:
        raise ValueError(f"The covariate '{covariate}' is not found in 'participants.tsv'.")

    # Check if confounds exist in the participants.tsv file
    if confounds:
        for confound in confounds:
            if confound not in participants_df.columns:
                raise ValueError(f"The confound '{confound}' is not found in 'participants.tsv'.")

    # List of columns to extract (measure and confounds)
    columns_to_extract = [covariate]
    if confounds:
        columns_to_extract.extend(confounds)
    
    # Create an empty DataFrame to store the extracted data
    extracted_data = pd.DataFrame()

    # Extract the measure and confounds for each subject in subjects_list
    for subject in subjects:
        # Find the row corresponding to the subject
        subject_row = participants_df.loc[participants_df['participant_id'] == 'sub-' + subject, columns_to_extract]
        
        # Check if the subject exists in the participants.tsv file
        if subject_row.empty:
            raise ValueError(f"Subject '{subject}' is not found in 'participants.tsv'.")
        
        # Append the subject's data to the extracted DataFrame
        extracted_data = pd.concat([extracted_data, subject_row])

    # Reset the index of the resulting DataFrame
    extracted_data.reset_index(drop=True, inplace=True)

    return extracted_data  # This is a DataFrame


# Helper function to select confounds
def select_confounds(confounds_file, config):
    """
    Extract confounds selected for denoising from fMRIPrep confounds file.

    Parameters
    ----------
    confounds_file : str or Path
        Path to fMRIPrep confounds file.
    config : dict
        Configuration dict.

    Raises
    ------
    ValueError
        If requested confound is not found in the columns of fMRIPrep confounds file.

    Returns
    -------
    selected_confounds : DataFrame
        Confounds to regression from fMRI signal.

    """
    confounds = pd.read_csv(confounds_file, delimiter='\t')
    
    # First check selected confound columns are valid names
    for confound_column in config.get("confound_columns"):
        if not confound_column in confounds.columns:
            raise ValueError(f"Confounds column {confound_column} is not a valid confound name.")
            
    # If aroma denoising is used, make sure confounds do not contain motion parameters and warn user
    if config["ica_aroma"]:
        motion_parameters = ["trans_x", "trans_x_derivative1", "trans_x_derivative1_power2", "trans_x_power2",
                             "trans_y", "trans_y_derivative1", "trans_y_derivative1_power2", "trans_y_power2",
                             "trans_z", "trans_z_derivative1", "trans_z_power2", "trans_z_derivative1_power2",
                             "rot_x", "rot_x_derivative1", "rot_x_derivative1_power2", "rot_x_power2",
                             "rot_y", "rot_y_derivative1", "rot_y_power2", "rot_y_derivative1_power2",
                             "rot_z", "rot_z_derivative1", "rot_z_power2", "rot_z_derivative1_power2"]
        for motion_parameter in motion_parameters:
            if motion_parameter  in config["confound_columns"]:
                config["confound_columns"].remove(motion_parameter)
                warnings.warn(f"Motion parameter {motion_parameter} is detected in the confounds list, but you have selected aroma-denoising, which already deals with motion paramters. Removing {motion_parameter} from the confounds list.")
    
    # Select the confounds
    selected_confounds = confounds[config.get("confound_columns")]
    
    # Deal with NaN in confound values
    # Todo: implement better method to deal with NaN's. Those are always present when taking derivatives of confounds and nilearn trows an error. Maybe a bug in nilearn? Open an issue?
    # warnings.warn("If NaNs are present in the confounds, they are replaced by zero to ensure compatibility with nilearn. This is potentially very wrong.")
    # selected_confounds = selected_confounds.fillna(0)
    return selected_confounds


# Helper function to load the configuration file
def load_config(config):
    """
    Load configuration either from dict or config file.

    Parameters
    ----------
    config : dict, str or Path
        If dict, a configuration dict. If str or Path, path to the configuration file to load.

    Raises
    ------
    FileNotFoundError
        If file to load configuration is not found.
    TypeError
        If type of config is not dict, str or Path.

    Returns
    -------
    dict
        Configuration dict.

    """
    
    if isinstance(config, dict):
        return config
    else:
        if isinstance(config, (str, Path)):
            config = Path(config)
            if not config.exists():
                raise FileNotFoundError(f"File not found: {config}")
                
            # Detect file extension
            file_extension = config.suffix.lower()
        
            # Load JSON file
            if file_extension == ".json":
                with open(config, 'r') as file:
                    return json.load(file)
        
            # Load YAML file
            elif file_extension in [".yaml", ".yml"]:
                with open(config, 'r') as file:
                    return yaml.safe_load(file)
            else:
                raise TypeError(f"Wrong configuration data {config}. Must provide either path (to .json or .yaml or .yml) or dict.")


def load_seed_file(seeds_file):
    # Read seed labels and coordinates from file
    if os.path.isfile(seeds_file):
        with open(seeds_file) as seeds_file:
            tsv_file = csv.reader(seeds_file, delimiter="\t")
            labels = []
            coords = []
            for line in tsv_file:
                labels.append(line[0])
                coords.append(np.array(line[1:4], dtype=int))
    else:
        raise FileNotFoundError(f"Seeds file {seeds_file} not found")
        
    # Remove spaces, dashes and underscores from labels
    labels = [label.replace('_', '').replace(' ', '').replace('-', '') for label in labels]
    
    # Verify that we still have a unique label for each seed
    if not len(labels) == len(set(labels)):
        raise ValueError(f"All labels loaded from {seeds_file} are not unique after removing spaces, dashes or underscores. Please correct this in your seeds file.")
    
    return coords, labels


# MAKERS
# Function to create directory in which path is located
def ensure_directory(file_path):
    """
    Ensure that the directory for a given file path exists.
    If it does not exist, create it.
    
    Args:
    file_path (str): The full path to the file, including the filename.

    Example:
    ensure_directory("/path/to/my/directory/filename.txt")
    """        
    Path(file_path).parents[0].mkdir(exist_ok=True, parents=True)


# Helper function to generate a dataset_description.json file
def create_dataset_description(output_dir):
    """
    Create the dataset_description.json file, mandatory if outputs are to be indexed by BIDSLayout.

    Parameters
    ----------
    output_dir : str or Path
        Path to the output dir where to save the description.

    Returns
    -------
    None.

    """
    description = {
        "Name": "connectomix",
        "BIDSVersion": "1.6.0",
        "PipelineDescription": {
            "Name": "connectomix",
            "Version": __version__,
            "CodeURL": "https://github.com/ln2t/connectomix"
        }
    }
    with open(output_dir / "dataset_description.json", 'w') as f:
        json.dump(description, f, indent=4)


def generate_group_analysis_report(layout, bids_entities, config):
    """
    Generates a group analysis report based on the method and connectivity kind.

    """

    method = config.get("method")
    analysis_label = config.get('analysis_label')
    connectivity_kinds = config.get("connectivity_kinds")
    analysis_type = config.get("analysis_type")
    
    entities = dict(**bids_entities ,
                    method=method,
                    analysis=analysis_label)
  
    report_output_path = layout.derivatives["connectomix"].build_path(entities,
                                                 path_patterns=['group/{analysis}/group_[ses-{session}_][run-{run}_]task-{task}_space-{space}_method-{method}_desc-{desc}_analysis-{analysis}_report.html'],
                                                 validate=False)
    
    ensure_directory(report_output_path)    
    
    suffixes = ['uncorrmatrix', 'uncorrconnectome', 'fdrmatrix', 'fdrconnectome', 'fwematrix', 'fweconnectome']

    with open(report_output_path, 'w') as report_file:
        # Write the title of the report
        report_file.write(f"<h1>Group analysis Report for Method: {method}</h1>\n")
        report_file.write(f"<h2>Connectivity Kind: {connectivity_kinds}</h2>\n")
        report_file.write(f"<h3>Analysis type: {analysis_type}, analysis label {config.get('analysis_label')}</h3>\n")
        if analysis_type == 'independent':
            report_file.write(f"<h3>Subjects: {config.get('group1_subjects')} versus {config.get('group2_subjects')}</h3>\n")
        elif analysis_type == 'regression':
            report_file.write(f"<h3>Subjects: {config.get('subjects_to_regress')}</h3>\n")
            report_file.write(f"<h3>Covariate: {config.get('covariate')}</h3>\n")
            if config.get('analysis_options')['confounds']:
                report_file.write(f"<h3>Confounds: {config.get('confounds')}</h3>\n")
        for suffix in suffixes:
            figure_files = layout.derivatives["connectomix"].get(**bids_entities,
                                                                 suffix=suffix,
                                                                 extension='.svg',
                                                                 return_type='filename')
            figure_files = apply_nonbids_filter('method', method, figure_files)
            
            figure_files = apply_nonbids_filter('analysis', analysis_label, figure_files)
            
            if suffix in ['uncorrmatrix', 'uncorrconnectome']:
                alpha = str(config["uncorrected_alpha"]).replace('.', 'dot')
            if suffix in ['fdrmatrix', 'fdrconnectome']:
                alpha = str(config["fdr_alpha"]).replace('.', 'dot')
            if suffix in ['fwematrix', 'fweconnectome']:
                alpha = str(config["fwe_alpha"]).replace('.', 'dot')
                
            figure_files = apply_nonbids_filter('alpha', alpha, figure_files)
            if len(figure_files) < 1:
                raise ValueError("Not enough figure files found, maybe this is a bug?")    
            elif len(figure_files) >= 2:
                raise ValueError("f{Too many files found in the group-level outputs, are you sure you aren't mixing up analyses? Use different labels if need be!'}")
            else:
                for figure_file in figure_files:
                    report_file.write(f'<img src="{figure_file}" width="800">\n')

        print("Group analysis report saved. To open, you may try to type the following command (with some minor modification if using Docker)")
        print(f"open {report_output_path}")


# Helper function to create and save connectome plots for each thresholding strategy
def generate_group_connectome_plots(t_stats, uncorr_mask, fdr_mask, perm_mask, config, layout, entities, coords):    
    """
    Same as generate_group_matrix_plots, but for the connectomes (i.e. glass-brains with connections represented as solid lines between nodes).

    Returns
    -------
    None.

    """
        
    fn_uncorr = layout.derivatives["connectomix"].build_path({**entities,
                                                      "analysis_label": config["analysis_label"],
                                                      "method": config["method"]   ,
                                                      "alpha": str(config["uncorrected_alpha"]).replace('.', 'dot')
                                                      },
                                                 path_patterns=["group/{analysis_label}/group_[ses-{session}_][run-{run}_]task-{task}_space-{space}_method-{method}_desc-{desc}_analysis-{analysis_label}_alpha-{alpha}_uncorrconnectome.svg"],
                                                 validate=False)
    
    fn_fdr = layout.derivatives["connectomix"].build_path({**entities,
                                                      "analysis_label": config["analysis_label"],
                                                      "method": config["method"] ,
                                                      "alpha": str(config["fdr_alpha"]).replace('.', 'dot')
                                                      },
                                                 path_patterns=["group/{analysis_label}/group_[ses-{session}_][run-{run}_]task-{task}_space-{space}_method-{method}_desc-{desc}_analysis-{analysis_label}_alpha-{alpha}_fdrconnectome.svg"],
                                                 validate=False)
    
    fn_fwe = layout.derivatives["connectomix"].build_path({**entities,
                                                      "analysis_label": config["analysis_label"],
                                                      "method": config["method"] ,
                                                      "alpha": str(config["fwe_alpha"]).replace('.', 'dot')
                                                      },
                                                 path_patterns=["group/{analysis_label}/group_[ses-{session}_][run-{run}_]task-{task}_space-{space}_method-{method}_desc-{desc}_analysis-{analysis_label}_alpha-{alpha}_fweconnectome.svg"],
                                                 validate=False)
    
    uncorr_percentage = 100*float(config.get("uncorrected_alpha"))
    uncorr_percentage = str(uncorr_percentage)
    plt.figure(figsize=(10, 10))
    plot_connectome(t_stats * uncorr_mask, node_coords=coords, title=f"Uncorrected Threshold ({uncorr_percentage}%)")
    plt.savefig(fn_uncorr)
    plt.close()

    fdr_percentage = 100*float(config.get("fdr_alpha"))
    fdr_percentage = str(fdr_percentage)
    plt.figure(figsize=(10, 10))
    plot_connectome(t_stats * fdr_mask, node_coords=coords, title=f"FDR Threshold ({fdr_percentage}%)")
    plt.savefig(fn_fdr)
    plt.close()

    fwe_percentage = 100*float(config.get("fwe_alpha"))
    fwe_percentage = str(fwe_percentage)
    n_permutations = config.get("n_permutations")
    n_permutations = str(n_permutations)
    plt.figure(figsize=(10, 10))
    plot_connectome(t_stats * perm_mask, node_coords=coords, title=f"Permutation-Based Threshold ({fwe_percentage}% and {n_permutations} permutations)")
    plt.savefig(fn_fwe)
    plt.close()


# Helper function to create and save matrix plots for each thresholding strategy
def generate_group_matrix_plots(t_stats, uncorr_mask, fdr_mask, perm_mask, config, layout, entities, labels=None):
    """
    Tool to generate thresholded connectivity matrix plots.

    Parameters
    ----------
    t_stats : numpy.array
        The unthresholded t-score matrix.
    uncorr_mask : numpy.array
        Mask defining the supra-threshold connections for the uncorrected strategy.
    fdr_mask : numpy.array
        Mask defining the supra-threshold connections for the fdr strategy.
    perm_mask : numpy.array
        Mask defining the supra-threshold connections for the fwe strategy.
    config : dict
        Configuration.
    layout : BIDSLayout
        Usual BIDS class for the dataset.
    entities : dict
        Entities to build output paths for the figures.
    labels : list, optional
        Labels for the axis of the plots (length is equal to the number of rows of the connectivity matrix). The default is None.

    Returns
    -------
    None.

    """
        
    fn_uncorr = layout.derivatives["connectomix"].build_path({**entities,
                                                      "analysis_label": config["analysis_label"],
                                                      "method": config["method"],
                                                      "alpha": str(config["uncorrected_alpha"]).replace('.', 'dot')
                                                      },
                                                 path_patterns=["group/{analysis_label}/group_[ses-{session}_][run-{run}_]task-{task}_space-{space}_method-{method}_desc-{desc}_analysis-{analysis_label}_alpha-{alpha}_uncorrmatrix.svg"],
                                                 validate=False)
    
    fn_fdr = layout.derivatives["connectomix"].build_path({**entities,
                                                      "analysis_label": config["analysis_label"],
                                                      "method": config["method"],
                                                      "alpha": str(config["fdr_alpha"]).replace('.', 'dot')
                                                      },
                                                 path_patterns=["group/{analysis_label}/group_[ses-{session}_][run-{run}_]task-{task}_space-{space}_method-{method}_desc-{desc}_analysis-{analysis_label}_alpha-{alpha}_fdrmatrix.svg"],
                                                 validate=False)
    
    fn_fwe = layout.derivatives["connectomix"].build_path({**entities,
                                                      "analysis_label": config["analysis_label"],
                                                      "method": config["method"],
                                                      "alpha": str(config["fwe_alpha"]).replace('.', 'dot')
                                                      },
                                                 path_patterns=["group/{analysis_label}/group_[ses-{session}_][run-{run}_]task-{task}_space-{space}_method-{method}_desc-{desc}_analysis-{analysis_label}_alpha-{alpha}_fwematrix.svg"],
                                                 validate=False)
    
    uncorr_percentage = 100*float(config.get("uncorrected_alpha"))
    uncorr_percentage = str(uncorr_percentage)
    plt.figure(figsize=(10, 10))
    plot_matrix(t_stats * uncorr_mask, labels=labels, colorbar=True, title=f"Uncorrected Threshold ({uncorr_percentage}%)")
    plt.savefig(fn_uncorr)
    plt.close()
    
    fdr_percentage = 100*float(config.get("fdr_alpha"))
    fdr_percentage = str(fdr_percentage)
    plt.figure(figsize=(10, 10))
    plot_matrix(t_stats * fdr_mask, labels=labels, colorbar=True, title=f"FDR Threshold ({fdr_percentage}%)")
    plt.savefig(fn_fdr)
    plt.close()

    fwe_percentage = 100*float(config.get("fwe_alpha"))
    fwe_percentage = str(fwe_percentage)    
    n_permutations = config.get("n_permutations")
    n_permutations = str(n_permutations)
    plt.figure(figsize=(10, 10))
    plot_matrix(t_stats * perm_mask, labels=labels, colorbar=True, title=f"Permutation-Based Threshold ({fwe_percentage}% and {n_permutations} permutations)")
    plt.savefig(fn_fwe)
    plt.close()
    

# Function to copy config to path
def save_copy_of_config(config, path):
    """
    Save a copy of config to path, for reproducibility.

    Parameters
    ----------
    config : dict or str or Path
        Configuration dict or path to loaded configuration file.
    path : str or Path
        Path to the desired location to dump the config.

    Returns
    -------
    None.

    """
    # First make sure destination is valid
    ensure_directory(path)
    # If config is a str, assume it is a path and copy
    if isinstance(config, (str, Path)):
        shutil.copy(config, path)
    # Otherwise, it is a dict and must be dumped to path
    elif isinstance(config, dict):
        with open(path, "w") as fp:
            json.dump(config, fp, indent=4)
    return None


# CONFIG
# Function to manage default group-level options
def set_unspecified_participant_level_options_to_default(config, layout):
    """
    Set the configuration fields to their default values if not explicitly specified in the input config.

    Parameters
    ----------
    config : dict
        Input configuration. Can be completely empty (config = {}).
    layout : BIDSLayout
        BIDS layout object of the dataset.

    Returns
    -------
    config : dict
        A complete configuration.

    """
    # BIDS stuff
    config["subject"] = config.get("subject", layout.derivatives['fMRIPrep'].get_subjects())  # Subjects to include in the analysis
    config["tasks"] = config.get("tasks", layout.derivatives['fMRIPrep'].get_tasks())  # Tasks to include in the analysis
    config["runs"] = config.get("runs", layout.derivatives['fMRIPrep'].get_runs())  # Runs to include in the analysis
    config["sessions"] = config.get("sessions", layout.derivatives['fMRIPrep'].get_sessions())  # Sessions to include in the analysis
    config["spaces"] = config.get("spaces", layout.derivatives['fMRIPrep'].get_spaces())  # Spaces to include in the analysis

    if 'MNI152NLin2009cAsym' in config.get("spaces"):
        config["spaces"] = ['MNI152NLin2009cAsym']  # First default to 'MNI152NLin2009cAsym'
    elif 'MNI152NLin6Asym' in config.get("spaces"):
        config["spaces"] = ['MNI152NLin6Asym']  # Second default to 'MNI152NLin6Asym' (useful when using ica-aroma denoising)
 
    # Analysis parameters
    config["method"] = config.get("method", "roiToVoxel")  # The method to define connectome, e.g. from a valid atlas name or "roiToVoxel"
    config["seeds_file"] = config.get("seeds_file", None)  # Path to file with seed coordinates for seed-based and roi-to-voxel
    config["radius"] = config.get("radius", 5)  # Radius of the sphere, in mm, for the seeds
    config["supported_atlases"] = ["schaeffer100", "aal", "harvardoxford"]  # This is not a user parameters but is used only internally
    
    # Preprocessing parameters
    config["reference_functional_file"] = config.get("reference_functional_file", "first_functional_file")  # Reference functional file for resampling
    config["high_pass"] = config.get("high_pass", 0.01)  # High-pass filter for data denoising - Default value from Ciric et al 2017
    config["low_pass"] = config.get("low_pass", 0.08)  # Low-pass filter for data denoising - Default value from Ciric et al 2017
    default_confound_columns = ['trans_x', 'trans_y', 'trans_z', 'rot_x', 'rot_y', 'rot_z', 'csf_wm']  # List of default signal confounds for denoising
    config["confound_columns"] = config.get("confound_columns", default_confound_columns)  # Signal confounds for denoising
    config["ica_aroma"] = config.get("ica_aroma", False)  # ICA-AROMA denoising

    if config["ica_aroma"]:  # For ICA-AROMA, default to space 'MNI152NLin6Asym'
        print("Defaulting to space MNI152NLin6Asym for ICA-AROMA denoising (overriding spaces from config file")
        config["spaces"] = ['MNI152NLin6Asym']
    elif "MNI152NLin6Asym" in config["spaces"]:
        warnings.warn("Space 'MNI152NLin6Asym' was found in the list of spaces and ica_aroma was disabled. To avoid name conflicts, we force you to use ica_aroma with MNI152NLin6Asym. For now, 'MNI152NLin6Asym' will be removed from the list of spaces.")
        config["spaces"] = [space for space in config["spaces"] if space != 'MNI152NLin6Asym']
    
    # Roi-to-roi specific parameters
    config["connectivity_kinds"] = config.get("connectivity_kinds", ["correlation"])  # The kind of connectivity measure, unused for roi-to-voxel
    # .. canica options
    config["canica_threshold"] = config.get('canica_threshold', 0.5)
    config["canica_min_region_size"] = config.get('canica_min_region_size', 50)    # Extract also regions from the canica components for connectivity analysis
    
    # Roi-to-voxel specific parameters
    config["roi_masks"] = config.get("roi_masks", None)  # List of path to mask for roi-to-voxel

    # Consistency checks
    # TODO: add more consistency checks!
    if config["method"] == "roiToVoxel" and (config["seeds_file"] is not None and config["roi_masks"] is not None):
        raise ValueError("Config fields 'seeds_file' and 'roi_masks' cannot both be defined when performing 'roiToVoxel' analyzes")
    
    # List-ify connectivity_kinds in case it was not set to a list in config by user
    if not isinstance(config["connectivity_kinds"], list):
        config["connectivity_kinds"] = [config["connectivity_kinds"]]

    return config

# Function to manage default group-level options
def set_unspecified_group_level_options_to_default(config, layout):
    """
    Set the configuration fields to their default values if not explicitly specified in the input config.

    Parameters
    ----------
    config : dict
        Input configuration. Can be completely empty (config = {}).
    layout : BIDSLayout
        BIDS layout object of the dataset.

    Returns
    -------
    config : dict
        A complete configuration.

    """
    
    # BIDS stuff
    config["subject"] = config.get("subject", layout.derivatives["connectomix"].get_subjects())  # Subjects to include in the analysis
    config["tasks"] = config.get("tasks", "restingstate" if "restingstate" in layout.derivatives["connectomix"].get_tasks() else layout.derivatives["connectomix"].get_tasks())
    config["runs"] = config.get("runs", layout.derivatives["connectomix"].get_runs())
    config["sessions"] = config.get("sessions", layout.derivatives["connectomix"].get_sessions())
    config["spaces"] = config.get("spaces", "MNI152NLin2009cAsym" if "MNI152NLin2009cAsym" in layout.derivatives["connectomix"].get_spaces() else layout.derivatives["connectomix"].get_spaces())
    
    # Participant-level parameters
    config["method"] = config.get("method", "roiToVoxel")
    config["seeds_file"] = config.get("seeds_file", None)  # Path to file with seed coordinates for seed-based and roi-to-voxel
    config["radius"] = config.get("radius", 5)
    config["roi_masks"] = config.get("roi_masks", None)  # List of path to mask for roi-to-voxel
    
    # Analysis parameters
    config["analysis_type"] = config.get("analysis_type", "independent")  # Options: 'independent' or 'paired' or 'regression'
    config["analysis_label"] = config.get("analysis_label", "CUSTOMNAME")
    config["smoothing"] = config.get("smoothing", 8)  # In mm, smoothing for the cmaps
    config["group_confounds"] = config.get("group_confounds", [])
    config["group_contrast"] = config.get("group_contrast", "intercept")

    # Stats and permutations
    config["uncorrected_alpha"] = config.get("uncorrected_alpha", 0.001)
    config["fdr_alpha"] = config.get("fdr_alpha", 0.05)
    config["fwe_alpha"]= float(config.get("fwe_alpha", 0.05))
    config["n_permutations"] = config.get("n_permutations", 20)
    
    # Toi-to-voxel parameters
    config["cluster_forming_alpha"] = config.get("cluster_forming_alpha", 0.01)  # p-value for cluster forming threshold in roiToVoxel analysiss
    
    # Roi-to-roi specific parameters
    config["connectivity_kinds"] = config.get("connectivity_kinds", ["correlation"])
    config["group1_subjects"] = config.get("group1_subjects", None)
    config["group2_subjects"] = config.get("group2_subjects", None)
    
    if config["analysis_type"] == 'independent' and config["group1_subjects"] is None:
        guessed_groups = guess_groups(layout)
        if len(guessed_groups) == 2:
            group1_name = list(guessed_groups.keys())[0]
            group2_name = list(guessed_groups.keys())[1]
            warnings.warn(f"Group have been guessed. Assuming group 1 is {group1_name} and group 2 is {group2_name}")
            config["group1_subjects"] = list(guessed_groups.values())[0]
            config["group2_subjects"] = list(guessed_groups.values())[1]
            config["analysis_label"] = f"{group1_name}VersuS{group2_name}"  # This overwrites the above generic name to ensure people don't get confused with the automatic selection of subjects
            warnings.warn(f"Setting analysis label to {config['analysis_label']}")
            config["group1_name"] = group1_name
            config["group2_name"] = group2_name
        else:
            config["group1_subjects"] = config.get("subjects", layout.derivatives["connectomix"].get_subjects())  # this is used only through the --helper tool (or the autonomous mode)
            warnings.warn("Could not detect two groups, putting all subjects into first group.")

    # List-ify connectivity_kinds in case it was not set to a list in config by user
    if not isinstance(config["connectivity_kinds"], list):
        config["connectivity_kinds"] = [config["connectivity_kinds"]]

    # analysis_options = {}
    
    # # If "analysis_options" is not set by user, then try to create it
    # if "analysis_options" not in config.keys():
    #     if config["analysis_type"] == 'regression':
    #         analysis_options["subjects_to_regress"] = layout.derivatives["connectomix"].get_subjects()
    #         analysis_options["covariate"] = "COVARIATENAME"
    #         analysis_options["confounds"] = []
    #     else:
            
    #         if config["analysis_type"] == 'independent':
                
    #             guessed_groups = guess_groups(layout)
    #             if len(guessed_groups) == 2:
    #                 group1_name = list(guessed_groups.keys())[0]
    #                 group2_name = list(guessed_groups.keys())[1]
    #                 warnings.warn(f"Group have been guessed. Assuming group 1 is {group1_name} and group 2 is {group2_name}")
    #                 analysis_options["group1_subjects"] = list(guessed_groups.values())[0]
    #                 analysis_options["group2_subjects"] = list(guessed_groups.values())[1]
    #                 config["analysis_label"] = f"{group1_name}VersuS{group2_name}"  # This overwrites the above generic name to ensure people don't get confused with the automatic selection of subjects
    #                 warnings.warn(f"Setting analysis label to {config['analysis_label']}")
    #                 analysis_options["group1_name"] = group1_name
    #                 analysis_options["group2_name"] = group2_name
    #             else:
    #                 config["group1_subjects"] = config.get("subjects", layout.derivatives["connectomix"].get_subjects())  # this is used only through the --helper tool (or the autonomous mode)
    #                 warnings.warn("Could not detect two groups, putting all subjects into first group.")
                    
    #         elif config["analysis_type"] == 'paired':
    #             analysis_options["subjects"] = layout.derivatives["connectomix"].get_subjects()
    #             analysis_options["sample1_entities"] = dict(tasks=config.get("tasks"),
    #                                                         sessions=config.get("sessions"),
    #                                                         runs=config.get("runs"))
    #             analysis_options["sample2_entities"] = analysis_options["sample1_entities"]  # This does not make sense, but is done only to help the user to fine-tune the config file manually.
                
    # TODO: add more checks that config has all required information to work
    # Set the analysis_options field
    # Todo: enable confounds to be optional in the config file. Currently it does not work if analysis_options are set in config file as it does not take the default value in the following line. But we want to be able to leave the confounds field empty in the config file.
    # config = config.get("analysis_options", analysis_options)
    
    # if config.get("method") == 'seeds' or config.get("method") == 'roiToVoxel':
    #     config["radius"] = config.get("radius", 5)
    
    return config

def create_participant_level_default_config_file(bids_dir, output_dir, fmriprep_dir):
    """
    Create default configuration file in YAML format for default parameters, at participant level.
    The configuration file is saved at 'derivatives_dir/config/default_participant_level_config.yaml'

    Parameters
    ----------
    bids_dir : str or Path
        Path to BIDS directory.
    output_dir : str or Path
        Path to derivatives.
    fmriprep_dir : str or Path
        Path to fMRIPrep derivatives.

    Returns
    -------
    None.

    """

    # Print some stuff for the primate using this function
    print("Generating default configuration file for default parameters, please wait while the dataset is explored...")
    
    # Create derivative directory        
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create the dataset_description.json file
    create_dataset_description(output_dir)

    # Create a BIDSLayout to parse the BIDS dataset
    layout = BIDSLayout(bids_dir, derivatives=[fmriprep_dir, output_dir])
    
    # Load all default values in config file
    config = set_unspecified_participant_level_options_to_default({}, layout)

    # Prepare the YAML content with comments
    yaml_content_with_comments = f"""\
# Connectomix Configuration File
# This file is generated automatically. Please modify the parameters as needed.
# Full documentation is located at github.com/ln2t/connectomix
# Important note: more parameters can be tuned than those shown here, this is only a starting point.

# List of subjects
subjects: {config.get("subjects")}

# List of tasks
tasks: {config.get("tasks")}

# List of runs
runs: {config.get("runs")}

# List of sessions
sessions: {config.get("sessions")}

# List of output spaces
spaces: {config.get("spaces")}

# Confounding variables to include when extracting timeseries. Choose from confounds computed from fMRIPrep.
confound_columns: {config.get("confound_columns")}

# Use ICA-AROMA denoised data or not. If set to True, fMRIPrep output must be further processed using fMRIPost-AROMA (see https://github.com/nipreps/fmripost-aroma)
ica_aroma: {config.get("ica_aroma")}

# Kind of connectivity measure to compute
connectivity_kind: {config.get("connectivity_kinds")}  # Choose from covariance, correlation, partial correlation or precision. This option is passed to nilearn.connectome.ConnectivityMeasure.

# Method to define regions of interests to compute connectivity
method: {config.get("method")} # Method to determine ROIs to compute variance. Uses the Schaeffer 2018 with 100 rois by default. More options are described in the documentation.
  
# Other parameters
high_pass: {config.get("high_pass")} # High-pass filtering, in Hz, applied to BOLD data. Low (<0.008 Hz) values does minimal changes to the signal, while high (>0.01) values improves sensitivity.
low_pass: {config.get("low_pass")} # Low-pass filtering, in Hz, applied to BOLD data. High (>0.1 Hz) values does minimal changes to the signal, while low (< 0.08 Hz)values improves specificity.
seeds_file: {config["seeds_file"]} # Path to seed file for seed-based ROIs
radius: {config["radius"]} # Radius, in mm, to create the spheres at the coordinates of the seeds for seed-based ROIs
    """
    
    # Build filenames for each output
    yaml_file = Path(output_dir) / 'config' / 'default_participant_level_config.yaml'
    
    ensure_directory(yaml_file)
    
    # Save the YAML content with comments
    with open(yaml_file, 'w') as yaml_out:
        yaml_out.write(yaml_content_with_comments)

    print(f"Default YAML configuration file saved at {yaml_file}. Go to github.com/ln2t/connectomix for more details.")
    print("See also below for the output:")
    print(yaml_content_with_comments)
    
# Helper function to create default configuration file based on what the dataset contains at group level
def create_group_level_default_config_file(bids_dir, output_dir):
    """
    Create default configuration file in YAML format for default parameters, at group level.
    Configuration file is saved at 'derivatives/config/default_group_level_config.yaml'.

    Parameters
    ----------
    bids_dir : str or Path
        Path to BIDS directory.
    derivatives_dir : str or Path
        Path to derivatives.

    Returns
    -------
    None.

    """

    # Create a BIDSLayout to parse the BIDS dataset
    layout = BIDSLayout(bids_dir, derivatives=[output_dir])

    # Print some stuff for the primate using this function
    print("Generating default configuration file for default parameters, please wait while the dataset is explored...")   
    
    # Load default configuration for several types of analysis
    independent_config = set_unspecified_group_level_options_to_default(dict(analysis_type='independent'), layout)
    paired_config = set_unspecified_group_level_options_to_default(dict(analysis_type='paired'), layout)
    regression_config = set_unspecified_group_level_options_to_default(dict(analysis_type='regression'), layout)
            
    # The default configuration is 'independet' but we also use the other ones in comments to help the user
    config = independent_config
    
    # Prepare the YAML content with comments
    yaml_content_with_comments = f"""\
# Connectomix Configuration File
# This file is generated automatically. Please modify the parameters as needed.
# Full documentation is located at github.com/ln2t/connectomix
# All parameters are set to their plausible or default value

analysis_label: {config.get("analysis_label")}  # Custom name for the analysis, e.g. ControlVersuSPatients, PreTreatmentVersuSPostTreatment, or EffectOfIQWithoutAge

# Analysis type
analysis_type: {config.get("analysis_type")}  # Choose from independent, paired, or regression. If regression is selected, provide also one covariate and optionnaly a list of confounds in analysis_options.

# Statistical alpha-level thresholds
uncorrected_alpha: {config.get("uncorrected_alpha")}  # Without multiple-comparison correction
fdr_alpha: {config.get("fdr_alpha")}  # Used in the BH-FDR multiple-comparison correction method
fwe_alpha: {config.get("fwe_alpha")}  # Used in the Family-Wise Error multiple-comparison correction method (maximum and minimum t-statistic distributions estimated from permutations of the data).

# Number of permutations to estimate the null distributions
n_permutations: {config.get("n_permutations")}  # Can be kept to a low value for testing purposes (e.g. 20). If increased, computational time goes up. Reliable results are expected for very large value, e.g. 10000.

# Selected task
tasks: {config.get("tasks")}

# Selected run
runs: {config.get("runs")}

# Selected session
sessions: {config.get("sessions")}

# Selected space
spaces: {config.get("spaces")}

# Groups to compare: names and subjects
group1_name: {config.get("group1_name")}
group2_name: {config.get("group2_name")}
group1_subjects: {config.get("group1_subjects")}
group2_subjects: {config.get("group2_subjects")}
# Paired analysis specifications
# subjects : {paired_config["subjects"]}  # Subjects to include in the paired analysis
# sample1_entities :  # These entities altogether must match exaclty two scans be subject
    # tasks: {paired_config["sample1_entities"]["tasks"]}
    # sessions: {paired_config["sample1_entities"]["sessions"]}
    # runs: {paired_config["sample1_entities"]["runs"]}
# sample2_entities : 
    # tasks: {paired_config["sample2_entities"]["tasks"]}
    # sessions: {paired_config["sample2_entities"]["sessions"]}
    # runs: {paired_config["sample2_entities"]["runs"]}
# Regression parameters
# subjects_to_regress: {regression_config.get("subjects_to_regress")}  # Subjects to include in the regression analysis
# covariate: {regression_config.get("covariate")}  # Covariate for analysis type 'regression'
# confounds: {regression_config.get("confounds")}  # Confounds for analysis type 'regression' (optionnal)

# Kind of connectivity used at participant-level
connectivity_kind: {config.get("connectivity_kinds")}

# Method used at participant-level
method: {config.get("method")}
    """
    
    # Build filenames for each output
    yaml_file = Path(output_dir) / 'config' / 'default_group_level_config.yaml'
    
    ensure_directory(yaml_file)
    
    # Save the YAML content with comments
    with open(yaml_file, 'w') as yaml_out:
        yaml_out.write(yaml_content_with_comments)

    print(f"Default YAML configuration file saved at {yaml_file}. Go to github.com/ln2t/connectomix for more details.")
    print("See also below for the output:")
    print(yaml_content_with_comments)




# PROCESSING
def img_is_not_empty(img):
    """
    Check if a NIfTI image has at least one non-zero voxel.
    """
    # Get the data array
    data = img.get_fdata()

    # Check if there is at least one non-zero voxel
    return np.any(data != 0)


# Function to resample all functional images to a reference image
def resample_to_reference(layout, func_files, config):
    """
    Resamples files to reference, and save the result to a BIDS compliant location.
    Skips resampling if file already exists.

    Parameters
    ----------
    layout : BIDSLayout
        Usual BIDS class for the dataset.
    func_files : list
        Paths to func files to resample.
    reference_img : str or Nifti1Image
        Rerefence image to which all the others will be resampled to.

    Returns
    -------
    resampled_files : list
        Paths to the resampled files.

    """
    
    # Choose the first functional file as the reference for alignment
    if config.get("reference_functional_file") == "first_functional_file":
        config["reference_functional_file"] = func_files[0]
    reference_img = load_img(config["reference_functional_file"])
    
    resampled_files = []
    for func_file in func_files:
        # Build BIDS-compliant filename for resampled data
        entities = layout.derivatives["connectomix"].parse_file_entities(func_file)
        resampled_path = layout.derivatives["connectomix"].build_path(entities,
                          path_patterns=['sub-{subject}/[ses-{session}/]sub-{subject}_[ses-{session}_][run-{run}_]task-{task}_space-{space}_desc-resampled.nii.gz'],
                          validate=False)
        
        ensure_directory(resampled_path)
        resampled_files.append(str(resampled_path))
        
        # Resample to reference if file does not exists
        if not os.path.isfile(resampled_path):
            img = load_img(func_file)
            # We round the affine as sometimes there are mismatch (small numerical errors?) in fMRIPrep's output
            img = Nifti1Image(img.get_fdata(), affine=np.round(img.affine, 2), header=img.header)
            if check_affines_match([img, reference_img]):
                resampled_img = img
            else:
                print("Doing some resampling, please wait...")
                resampled_img = resample_img(img, target_affine=reference_img.affine, target_shape=reference_img.shape[:3], interpolation='nearest')
                
            resampled_img.to_filename(resampled_path)
        else:
            print(f"Functional file {os.path.basename(resampled_path)} already exist, skipping resampling.")
    return resampled_files


# Compute CanICA component images
def compute_canica_components(layout, func_filenames, config):
    """
    Wrapper for nilearn.decomposition.CanICA. Computes group-level ICA components as well as extracts connected regions from the decomposition.

    Parameters
    ----------
    func_filenames : list
        List of path to func files from which to compute the components.
    layout : BIDSLayout
        Layout of the BIDS dataset, including relevant derivatives.
    entities : dict
        BIDS entities to build paths for the output files.
    options : dict
        Options to be passed to the region extractor.

    Returns
    -------
    canica_filename : str
        Path to the savec canica components image.
    extractor : Extractor
        Extractor object from the nilearn package (and already fit to the data at hand).

    """
    
    entities = get_bids_entities_from_config(config)
    entities.pop('subject')
    
    # Build path to save canICA components
    canica_filename = layout.derivatives["connectomix"].build_path(entities,
                      path_patterns=["canica/[ses-{session}_][run-{run}_]task-{task}_space-{space}_canicacomponents.nii.gz"],
                      validate=False)
    canica_sidecar = layout.derivatives["connectomix"].build_path(entities,
                     path_patterns=["canica/[ses-{session}_][run-{run}_]task-{task}_space-{space}_canicacomponents.json"],
                     validate=False)
    extracted_regions_filename = layout.derivatives["connectomix"].build_path(entities,
                      path_patterns=["canica/[ses-{session}_][run-{run}_]task-{task}_space-{space}_extractedregions.nii.gz"],
                      validate=False)
    extracted_regions_sidecar = layout.derivatives["connectomix"].build_path(entities,
                      path_patterns=["canica/[ses-{session}_][run-{run}_]task-{task}_space-{space}_extractedregions.json"],
                      validate=False)
        
    ensure_directory(canica_filename)
    ensure_directory(canica_sidecar)
    ensure_directory(extracted_regions_filename)
    ensure_directory(extracted_regions_sidecar)
    
    # Define canica parameters
    # Todo: ensure the options in CanICA are adapted
    canica_parameters = dict(n_components=20,
                             memory="nilearn_cache",
                             memory_level=2,
                             verbose=10,
                             mask_strategy="whole-brain-template",
                             random_state=0,
                             standardize="zscore_sample",
                             n_jobs=2)
    
    # Dump config to file for reproducibility
    with open(canica_sidecar, "w") as fp:
        json.dump({**canica_parameters, "func_filenames": func_filenames}, fp, indent=4)
    
    # If has not yet been computed, compute canICA components
    if not os.path.isfile(canica_filename):
        canica = CanICA(**canica_parameters)
        canica.fit(func_filenames)
        
        # Save image to output filename
        print(f"Saving canica components image to {canica_filename}")
        canica.components_img_.to_filename(canica_filename)
    else:
        print(f"ICA component file {os.path.basename(canica_filename)} already exist, skipping computation.")
    
    extractor_options = dict(threshold=config["canica_threshold"],
                             min_region_size=config["canica_min_region_size"],
                             standardize="zscore_sample",
                             detrend=True)
        
    # Dump config to file for reproducibility
    with open(extracted_regions_sidecar, "w") as fp:
        json.dump(extractor_options, fp, indent=4)
        
    # Extract regions from canica components
    extractor = RegionExtractor(
        canica_filename,
        **extractor_options
    )
    extractor.fit()
    
    print(f"Number of ICA-based components extracted: {extractor.regions_img_.shape[-1]}")
    
    print(f"Saving extracted ROIs to {extracted_regions_filename}")
    extractor.regions_img_.to_filename(extracted_regions_filename)
    
    config['components'] = canica_filename
    config['extractor'] = extractor
    
    return config

def denoise_fmri_data(layout, resampled_files, confound_files, json_files, config):
    """
    Tool to denoise fmri files based on confounds specified in config.

    Parameters
    ----------
    layout : BIDSLayout
    resampled_files : str or Path
    confound_files: str or Path
    json_files: str or Path
    config : dict

    Returns
    -------
    denoised_files : list
    """
    
    # Denoise the data
    denoised_paths = []
    for (func_file, confound_file, json_file) in zip(resampled_files, confound_files, json_files):
        print(f"Denoising file {func_file}")
        entities = layout.parse_file_entities(func_file)
        denoised_path = func_file if config['ica_aroma'] else layout.derivatives["connectomix"].build_path(entities,
                                                  path_patterns=['sub-{subject}/[ses-{session}/]sub-{subject}_[ses-{session}_][run-{run}_]task-{task}_space-{space}_denoised.nii.gz'],
                                                  validate=False)
        denoised_paths.append(denoised_path)
        
        if not Path(denoised_path).exists():
            print("Data denoising in progress")
            ensure_directory(denoised_path)
            
            confounds = select_confounds(str(confound_file), config)

            # Set filter options based on the config file
            high_pass = config['high_pass']
            low_pass = config['low_pass']
            
            clean_img(func_file,
                        low_pass=low_pass,
                        high_pass=high_pass,
                        t_r=get_repetition_time(json_file),
                        confounds=confounds).to_filename(denoised_path)
        else:
            print(f"Denoised data {denoised_path} already exists, skipping.")
    return denoised_paths

def glm_analysis_participant_level(json_file, mask_img, func_file, timeseries):
    
    t_r = get_repetition_time(json_file)
    glm = FirstLevelModel(t_r=t_r,
                          mask_img=resample_to_img(mask_img,
                                                func_file,
                                                interpolation="nearest"),
                          high_pass=None)
    frame_times = np.arange(len(timeseries)) * t_r
    design_matrix = make_first_level_design_matrix(frame_times=frame_times,
                                                   events=None,
                                                   hrf_model=None,
                                                   drift_model=None,
                                                   add_regs=timeseries)
    
    glm.fit(run_imgs=str(func_file),
            design_matrices=design_matrix)
    
    contrast_vector = np.array([1] + [0] * (design_matrix.shape[1] - 1))
    return glm.compute_contrast(contrast_vector, output_type="effect_size")

def save_roi_to_voxel_map(layout, roi_to_voxel_img, entities, label, config):
    # Create plot of z-score map and save
    roi_to_voxel_plot_path = layout.derivatives["connectomix"].build_path(entities,
                                              path_patterns=['sub-{subject}/[ses-{session}/]sub-{subject}_[ses-{session}_][run-{run}_]task-{task}_space-{space}_method-%s_seed-%s_plot.svg' % (config["method"], label)],
                                              validate=False)
    ensure_directory(roi_to_voxel_plot_path)
    
    if config["seeds_file"] is not None:
        coords, labels = load_seed_file(config["seeds_file"])
        coord = coords[labels.index(label)]
        
        roi_to_voxel_plot = plot_stat_map(roi_to_voxel_img,
                                          title=f"seed-to-voxel effect size for seed {label} (coords {coords})",
                                          cut_coords=coord)
        roi_to_voxel_plot.add_markers(marker_coords=[coord],
                                      marker_color="k",
                                      marker_size=2*config["radius"])
    else:
        roi_to_voxel_plot = plot_stat_map(roi_to_voxel_img,
                                          title=f"roi-to-voxel effect size for roi {label}")

    roi_to_voxel_plot.savefig(roi_to_voxel_plot_path)


def make_second_level_input(layout, label, config):
    second_level_input = pd.DataFrame(columns=['subject_label', 'map_name', 'effects_map_path'])
    entities = get_bids_entities_from_config(config)
    map_files = layout.derivatives["connectomix"].get(return_type='filename',
                                          extension='.nii.gz',
                                          **entities)
    map_files = apply_nonbids_filter('seed', label, map_files)
    map_files = apply_nonbids_filter('method', config['method'], map_files)
    
    # TODO: for paired analysis, compute difference of maps and save result to folder.
    if config['analysis_type'] == 'paired':
        raise ValueError('Paired analysis not yet supported')
    
    for file in map_files:
        file_entities = layout.parse_file_entities(file)
        second_level_input.loc[len(second_level_input)] = [f"sub-{file_entities['subject']}", label, file]
    
    return second_level_input

def get_group_level_confounds(layout, subjects_label, config):
    participants_file = layout.get(return_type="filename", extension="tsv", scope="raw")[0]
    participants_df = pd.read_csv(participants_file, sep='\t')
    
    if not isinstance(config["group_confounds"], list):
        config["group_confounds"] = [config["group_confounds"]]
    
    confounds = participants_df[["participant_id", *config["group_confounds"]]]
    confounds = confounds.rename(columns={"participant_id": "subject_label"}).copy()
    
    if "group" in config["group_confounds"]:
        group_labels = set(confounds["group"].values)
        
        for group in group_labels:
            confounds[group] = 0
            confounds.loc[confounds["group"] == group, group] = 1
        
        confounds.drop(columns=["group"], inplace=True)

    confounds.rename(columns={"participant_id": "subject_label"}, inplace=True)
    
    return None if len(confounds.columns) == 1 else confounds

def make_group_level_design_matrix(layout, second_level_input, label, config):
    subjects_label = list(second_level_input["subject_label"])
    confounds = get_group_level_confounds(layout, subjects_label, config)
    
    design_matrix = make_second_level_design_matrix(subjects_label, confounds=confounds)
    
    if "group" in config["group_confounds"]:
        design_matrix.drop(columns=["intercept"], inplace=True)
    
    entities = get_bids_entities_from_config(config)
    entities.pop("subject")
    design_matrix_plot_path = layout.derivatives["connectomix"].build_path({**entities,
                                                      "analysis_label": config["analysis_label"],
                                                      "method": config["method"],
                                                      "seed": label
                                                      },
                                                 path_patterns=["group/{analysis_label}/group_[ses-{session}_][run-{run}_][task-{task}]_space-{space}_method-{method}_seed-{seed}_analysis-{analysis_label}_designMatrix.svg"],
                                                 validate=False)
    ensure_directory(design_matrix_plot_path)
    plot_design_matrix(design_matrix, output_file=design_matrix_plot_path)
    
    return design_matrix

def compute_group_level_contrast(layout, glm, label, config):
    entities = get_bids_entities_from_config(config)
    entities.pop("subject")
    entities["seed"] = label
    contrast_label = config["group_contrast"]
    contrast_path = layout.derivatives["connectomix"].build_path({**entities,
                                                      "analysis_label": config["analysis_label"],
                                                      "method": config["method"],
                                                      "seed": label
                                                      },
                                                 path_patterns=["group/{analysis_label}/group_[ses-{session}_][run-{run}_][task-{task}]_space-{space}_method-{method}_seed-{seed}_analysis-{analysis_label}_zScore.nii.gz"],
                                                 validate=False)
    
    ensure_directory(contrast_path)
    glm.compute_contrast(contrast_label,
                         first_level_contrast=label, 
                         output_type="z_score").to_filename(contrast_path)
    return contrast_path

def save_group_level_contrast_plots(layout, contrast_path, coord, label, config):
    # Create plot of contrast map and save
    entities = get_bids_entities_from_config(config)
    entities.pop("subject")
    entities["seed"] = label
    contrast_plot_path = layout.derivatives["connectomix"].build_path({**entities,
                                                      "analysis_label": config["analysis_label"],
                                                      "method": config["method"],
                                                      "seed": label
                                                      },
                                              path_patterns=["group/{analysis_label}/group_[ses-{session}_][run-{run}_][task-{task}]_space-{space}_method-{method}_seed-{seed}_analysis-{analysis_label}_zScore.svg"],
                                              validate=False)
    ensure_directory(contrast_plot_path)
    contrast_plot = plot_stat_map(contrast_path,
                                  threshold=3.0,
                                  title=f"roi-to-voxel contrast for seed {label} (coords {coord})",
                                  cut_coords=coord)
    contrast_plot.add_markers(marker_coords=[coord],
                              marker_color="k",
                              marker_size=2*config["radius"])
    contrast_plot.savefig(contrast_plot_path)

def compute_non_parametric_max_mass(layout, glm, label, config):
    entities = get_bids_entities_from_config(config)
    entities.pop("subject")
    entities["seed"] = label
    np_logp_max_mass_path = layout.derivatives["connectomix"].build_path({**entities,
                                                       "analysis_label": config["analysis_label"],
                                                       "method": config["method"],
                                                       "seed": label
                                                       },
                                                  path_patterns=["group/{analysis_label}/group_[ses-{session}_][run-{run}_][task-{task}]_space-{space}_method-{method}_seed-{seed}_analysis-{analysis_label}_logpMaxMass.nii.gz"],
                                                  validate=False)
     
    ensure_directory(np_logp_max_mass_path)
    np_outputs = non_parametric_inference(glm.second_level_input_,
           design_matrix=glm.design_matrix_,
           second_level_contrast=config["group_contrast"],
           first_level_contrast=label,
           smoothing_fwhm=config["smoothing"],
           two_sided_test=True,  # TODO: put this in config file
           n_jobs=2,  # TODO: put this in config file
           threshold=float(config["cluster_forming_alpha"]),
           n_perm=config["n_permutations"])
    np_outputs["logp_max_mass"].to_filename(np_logp_max_mass_path)
    return np_logp_max_mass_path

def save_significant_contrast_maps(layout, contrast_path, np_logp_max_mass_path, label, config):
    for significance_level in ["uncorrected", "fdr", "fwe"]:
        alpha = float(config[f"{significance_level}_alpha"])
        entities = get_bids_entities_from_config(config)
        entities.pop("subject")
        entities["seed"] = label
        thresholded_contrast_path = layout.derivatives["connectomix"].build_path({**entities,
                                                          "analysis_label": config["analysis_label"],
                                                          "method": config["method"],
                                                          "seed": label,
                                                          "significance_level":significance_level
                                                          },
                                                     path_patterns=["group/{analysis_label}/group_[ses-{session}_][run-{run}_][task-{task}]_space-{space}_method-{method}_seed-{seed}_analysis-{analysis_label}_{significance_level}.nii.gz"],
                                                     validate=False)
        ensure_directory(thresholded_contrast_path)
        
        match significance_level:
            case "uncorrected":
                thresholded_img, _ = threshold_stats_img(contrast_path, alpha=alpha, height_control=None, two_sided=True)
                thresholded_img.to_filename(thresholded_contrast_path)
            case "fdr":
                thresholded_img, _ = threshold_stats_img(contrast_path, alpha=alpha, height_control="fdr", two_sided=True)
                thresholded_img.to_filename(thresholded_contrast_path)
            case "fwe":
                mask = math_img(f"img >= -np.log10({alpha})", img = np_logp_max_mass_path)
                mask = binarize_img(mask)
                
                if img_is_not_empty(mask):
                    masked_data = apply_mask(contrast_path, mask)
                    unmask(masked_data, mask).to_filename(thresholded_contrast_path)
                else:
                    warnings.warn(f"For map {contrast_path}, no voxel survives FWE thresholding at alpha level {alpha}.")


def save_max_mass_plot(layout, np_logp_max_mass_path, label, coords, config):
    entities = get_bids_entities_from_config(config)
    entities.pop("subject")
    entities["seed"] = label
    np_logp_max_mass_plot_path = layout.derivatives["connectomix"].build_path({**entities,
                                                      "analysis_label": config["analysis_label"],
                                                      "method": config["method"],
                                                      "seed": label
                                                      },
                                                 path_patterns=["group/{analysis_label}/group_[ses-{session}_][run-{run}_][task-{task}]_space-{space}_method-{method}_seed-{seed}_analysis-{analysis_label}_logpMaxMass.svg"],
                                                 validate=False)
    ensure_directory(np_logp_max_mass_plot_path)
    plot_glass_brain(
                    np_logp_max_mass_path,
                    colorbar=True,
                    cmap="autumn",
                    vmax=2.69,  # this is hardcoded but that's not a problem as it is only for plots
                    display_mode="z",
                    plot_abs=False,
                    cut_coords=coords,
                    threshold=-np.log10(float(config["fwe_alpha"]))).savefig(np_logp_max_mass_plot_path)


def roi_to_voxel_participant_analysis(layout, func_file, json_file, timeseries_list, labels, config):
    """
    Run roi-to-voxel analysis on denoised data. Save the outputs in BIDS derivative format.

    Parameters
    ----------
    layout : BIDSLayout
    func_files : list
    json_files : list
    config : dict

    Returns
    -------
    None.

    """
    entities = layout.parse_file_entities(func_file)
    mask_img = get_mask(layout, entities)
    
    for timeseries, label in zip(timeseries_list.T, labels):
        roi_to_voxel_img = glm_analysis_participant_level(json_file, mask_img, func_file, timeseries.reshape(-1, 1))
        
        roi_to_voxel_path = layout.derivatives["connectomix"].build_path(entities,
                                                  path_patterns=["sub-{subject}/[ses-{session}/]sub-{subject}_[ses-{session}_][run-{run}_]task-{task}_space-{space}_method-%s_seed-%s_effectSize.nii.gz" % (config["method"], label)],
                                                  validate=False)
        roi_to_voxel_img.to_filename(roi_to_voxel_path)
        
        save_roi_to_voxel_map(layout, roi_to_voxel_img, entities, label, config)
        
def roi_to_roi_participant_analysis(layout, func_file, json_file, timeseries_list, labels, config):
    """
    Run roi-to-roi analysis on denoised data. Save the outputs in BIDS derivative format.

    Parameters
    ----------
    layout : BIDSLayout
    func_files : list
    json_files : list
    config : dict

    Returns
    -------
    None.

    """
    connectivity_kinds = setup_and_check_connectivity_kinds(config)
    entities = layout.parse_file_entities(func_file)
    
    # Iterate over each connectivity type
    for connectivity_kind in connectivity_kinds:
        print(f"Computing connectivity: {connectivity_kind}")
        # Compute connectivityconnectivity_measure
        connectivity_measure = ConnectivityMeasure(kind=connectivity_kind)
        conn_matrix = connectivity_measure.fit_transform([timeseries_list])[0]
        
        # Mask out the major diagonal
        np.fill_diagonal(conn_matrix, 0)
    
        # Generate the BIDS-compliant filename for the connectivity matrix and save
        conn_matrix_path = layout.derivatives["connectomix"].build_path(entities,
                                                  path_patterns=["sub-{subject}/[ses-{session}/]sub-{subject}_[ses-{session}_][run-{run}_]task-{task}_space-{space}_method-%s_desc-%s_matrix.npy" % (config["method"], connectivity_kind)],
                                                  validate=False)
        ensure_directory(conn_matrix_path)
        np.save(conn_matrix_path, conn_matrix)
        
        # Generate the BIDS-compliant filename for the figure, generate the figure and save
        conn_matrix_plot_path = layout.derivatives["connectomix"].build_path(entities,
                                                  path_patterns=["sub-{subject}/[ses-{session}/]sub-{subject}_[ses-{session}_][run-{run}_]task-{task}_space-{space}_method-%s_desc-%s_matrix.svg" % (config["method"], connectivity_kind)],
                                                  validate=False)
        ensure_directory(conn_matrix_plot_path)
        plt.figure(figsize=(10, 10))
        plot_matrix(conn_matrix, labels=labels, colorbar=True)
        plt.savefig(conn_matrix_plot_path)
        plt.close()

def roi_to_voxel_group_analysis(layout, config):
    
    entities = get_bids_entities_from_config(config)
    entities.pop("subject")
    
    if config["seeds_file"]:
        coords, labels = load_seed_file(config["seeds_file"])
    elif config["roi_masks"]:
        labels = list(config["roi_masks"].keys())
        coords = None
    
    # TODO: add check at group level that config file should either have seeds_file OR roi_masks
    
    for label in labels:
        second_level_input = make_second_level_input(layout, label, config)  # get all first-level maps. In paired case, compute differences. Resamples and save all in folder.
        design_matrix = make_group_level_design_matrix(layout, second_level_input, label, config)

        glm = SecondLevelModel(smoothing_fwhm=config["smoothing"])
        glm.fit(second_level_input, design_matrix=design_matrix)
        
        contrast_path = compute_group_level_contrast(layout, glm, label, config)

        # TODO: there is caveat in this: it does not show the sign of t-score! Direction of effect unknown...
        np_logp_max_mass_path = compute_non_parametric_max_mass(layout, glm, label, config)
    
        save_significant_contrast_maps(layout, contrast_path, np_logp_max_mass_path, label, config)
    
    if coords:
        for coord, label in zip(coords, labels):
            save_group_level_contrast_plots(layout, contrast_path, coord, label, config)
            save_max_mass_plot(layout, np_logp_max_mass_path, label, coord, config)
    
def roi_to_roi_group_analysis(layout, config):
    
    for connectivity_kind in config.get("connectivity_kinds"):
        # Retrieve connectivity type and other configuration parameters
        method = config.get("method")
        task = config.get("tasks")
        run = config.get("runs")
        session = config.get("sessions")
        space = config.get("spaces")
        analysis_type = config.get("analysis_type")  # Label for the analysis, e.g. "independent"
        
        entities = {
            "task": task,
            "space": space,
            "session": session,
            "run": run,
            "desc": connectivity_kind
        }
    
        design_matrix = None  # This will be necessary for regression analyses
    
        # Perform the appropriate group-level analysis
        if analysis_type == "independent":
            # Load group specifications from config
            # Todo: change terminology from "group" to "samples" when performing independent samples tests so that it is consistent with the terminology when doing a paired test.
            group1_subjects = config["group1_subjects"]
            group2_subjects = config["group2_subjects"]
                
            # Check each group has at least two subjects, otherwise no permutation testing is possible
            check_group_has_several_members(group1_subjects)
            check_group_has_several_members(group2_subjects)
            
            # Retrieve the connectivity matrices for group 1 and group 2 using BIDSLayout
            group1_matrices = retrieve_connectivity_matrices_from_particpant_level(group1_subjects, layout, entities, method)
            group2_matrices = retrieve_connectivity_matrices_from_particpant_level(group2_subjects, layout, entities, method)
            
            # For independent tests we dontt need to keep track of subjects labels
            group1_matrices = list(group1_matrices.values())
            group2_matrices = list(group2_matrices.values())
        
            print(f"Group 1 contains {len(group1_matrices)} participants: {group1_subjects}")
            print(f"Group 2 contains {len(group2_matrices)} participants: {group2_subjects}")
            
            # Convert to 3D arrays: (subjects, nodes, nodes)
            group1_data = np.stack(group1_matrices, axis=0)
            group2_data = np.stack(group2_matrices, axis=0)
            group_data = [group1_data, group2_data]
            
            # Independent t-test between different subjects
            t_stats, p_values = ttest_ind(group1_data, group2_data, axis=0, equal_var=False)
    
        elif analysis_type == "paired":
            # Paired t-test within the same subjects
            paired_samples = retrieve_connectivity_matrices_for_paired_samples(layout, entities, config)
            
            # Get the two samples from paired_samples (with this we are certain that they are in the right order)
            sample1 = np.array(list(paired_samples.values()))[:,0]
            sample2 = np.array(list(paired_samples.values()))[:,1]
            group_data = [sample1, sample2]
            
            if len(sample1) != len(sample2):
                raise ValueError("Paired t-test requires an equal number of subjects in both samples.")
                
            t_stats, p_values = ttest_rel(sample1, sample2, axis=0)
            
            entities = remove_pair_making_entity(entities)
                
        elif analysis_type == "regression":
            subjects = config["subjects_to_regress"]
            group_data = retrieve_connectivity_matrices_from_particpant_level(subjects, layout, entities, method)
            group_data = list(group_data.values())
            design_matrix = retrieve_info_from_participant_table(layout, subjects, config["covariate"], config["confounds"])
            t_stats, p_values = regression_analysis(group_data, design_matrix)
        else:
            raise ValueError(f"Unknown analysis type: {analysis_type}")
            
        # Threshold 1: Uncorrected p-value
        uncorr_alpha = config["uncorrected_alpha"]
        uncorr_mask = p_values < uncorr_alpha
    
        # Threshold 2: FDR correction
        fdr_alpha = config["fdr_alpha"]
        fdr_mask = multipletests(p_values.flatten(), alpha=fdr_alpha, method="fdr_bh")[0].reshape(p_values.shape)
    
        # Threshold 3: Permutation-based threshold
        n_permutations = config["n_permutations"]
        if n_permutations < 5000:
            warnings.warn(f"Running permutation analysis with less than 5000 permutations (you chose {n_permutations}).")
            
        null_max_distribution, null_min_distribution = generate_permuted_null_distributions(group_data, config, layout, entities, {"observed_t_max": np.nanmax(t_stats), "observed_t_min": np.nanmin(t_stats)}, design_matrix=design_matrix)
        
        # Compute thresholds at desired significance
        fwe_alpha = float(config["fwe_alpha"])
        t_max = np.percentile(null_max_distribution, (1 - fwe_alpha / 2) * 100)
        t_min = np.percentile(null_min_distribution, fwe_alpha / 2 * 100)
        print(f"Thresholds for max and min stat from null distribution estimated by permutations: {t_max} and {t_min} (n_perms = {n_permutations})")
        
        perm_mask = (t_stats > t_max) | (t_stats < t_min)
        
        # Save thresholds to a BIDS-compliant JSON file
        thresholds = {
            "uncorrected_alpha": uncorr_alpha,
            "fdr_alpha": fdr_alpha,
            "fwe_alpha": fwe_alpha,
            "fwe_permutations_results": {
                "max_t": t_max,
                "min_t": t_min,
                "n_permutations": n_permutations
            }
        }
        
        threshold_file = layout.derivatives["connectomix"].build_path({**entities,
                                                          "analysis_label": config["analysis_label"],
                                                          "method": config["method"]                                                      
                                                          },
                                                     path_patterns=["group/{analysis_label}/group_[ses-{session}_][run-{run}_][task-{task}]_space-{space}_method-{method}_desc-{desc}_analysis-{analysis_label}_thresholds.json"],
                                                     validate=False)
        
        ensure_directory(threshold_file)
        with open(threshold_file, "w") as f:
            json.dump(thresholds, f, indent=4)
        
        # Get ROIs coords and labels for plotting purposes
        if method == "seeds":
            coords, labels = load_seed_file(config["seeds_file"])
            
        elif method == "ica":
            extracted_regions_entities = entities.copy()
            extracted_regions_entities.pop("desc")
            extracted_regions_entities["suffix"] = "extractedregions"
            extracted_regions_entities["extension"] = ".nii.gz"
            extracted_regions_filename = layout.derivatives["connectomix"].get(**extracted_regions_entities)[0]
            coords=find_probabilistic_atlas_cut_coords(extracted_regions_filename)
            labels = None
        else:
            # Handle the case where method is an atlas
            _, labels, coords = get_atlas_data(method, get_cut_coords=True)
    
        # Create plots of the thresholded group connectivity matrices and connectomes
        generate_group_matrix_plots(t_stats,
                                    uncorr_mask,
                                    fdr_mask,
                                    perm_mask,
                                    config,
                                    layout,
                                    entities,
                                    labels)
        
        generate_group_connectome_plots(t_stats,
                                        uncorr_mask,
                                        fdr_mask,
                                        perm_mask,
                                        config,
                                        layout,
                                        entities,
                                        coords)
        
        # Refresh BIDS indexing of the derivatives to find data for the report
        output_dir = layout.derivatives["connectomix"].root
        layout.derivatives.pop("connectomix")
        layout.add_derivatives(output_dir)
        
        # Generate report
        generate_group_analysis_report(layout, entities, config)

# Extract time series based on specified method
def extract_timeseries(func_file, t_r, config):
    """
    Extract timeseries from fMRI data on Regions-Of-Interests (ROIs).

    Parameters
    ----------
    func_file : str or Path
        Path to fMRI data.
    t_r : float
        Repetition Time.
    config : dict
        Configuration parameters.

    Raises
    ------
    FileNotFoundError
        When ROIs are defined using seeds, the seeds are read from a seeds file. This error is raised if the seeds file is not found.

    Returns
    -------
    timeseries : numpy.array
        The extracted time series. Shape is number of ROIs x number of timepoints.
    labels : list
        List of ROIs labels, in the same order as in timeseries.

    """

    method = config["method"]
    
    if method == "seeds" or (method == "roiToVoxel" and config["seeds_file"] is not None):
        coords, labels = load_seed_file(config["seeds_file"])
        
        radius = config["radius"]
        masker = NiftiSpheresMasker(
            seeds=coords,
            radius=float(radius),
            standardize="zscore_sample",
            detrend=False,
            high_pass=None,
            low_pass=None,
            t_r=t_r  # TODO: check if tr is necessary when filtering is not applied
        )
        timeseries = masker.fit_transform(func_file)
    if method in config["supported_atlases"] or (method == "roiToVoxel" and config["roi_masks"] is not None):
        if method in config["supported_atlases"]:
            imgs, labels, _ = get_atlas_data(method)
            imgs = [imgs]
        else:
            labels = list(config["roi_masks"].keys())
            imgs = list(config["roi_masks"].values())
            
            for roi_path in imgs:
                if not os.path.isfile(roi_path):
                    raise FileNotFoundError(f"No file found at provided path {roi_path} for roi_mask. Please review your configuration.")
            
        timeseries = []
        for img in imgs:
            masker = NiftiLabelsMasker(
                labels_img=img,
                standardize="zscore_sample",
                detrend=False,
                high_pass=None,
                low_pass=None,
                t_r=t_r  # TODO: check if tr is necessary when filtering is not applied
            )
            timeseries.append(masker.fit_transform(func_file))
        timeseries = np.hstack(timeseries)
    if method == "ica":
        # ICA-based extraction
        extractor = config["extractor"]
        extractor.high_pass = None
        extractor.low_pass  = None
        extractor.t_r = t_r
        timeseries = extractor.transform(func_file)
        labels = None

    return timeseries, labels

# STATS
# Permutation testing with stat max thresholding
def generate_permuted_null_distributions(group_data, config, layout, entities, observed_stats, design_matrix=None):
    """
    Perform a two-sided permutation test to determine positive and negative thresholds separately.
    Returns separate maximum and minimum thresholds for positive and negative t-values.
    """   
    # Todo: create plots of null distributions for the report
    # Extract values from config
    n_permutations = config.get("n_permutations")
    analysis_type = config.get("analysis_type")
    
    # Load pre-existing permuted data, if any
    perm_files = layout.derivatives["connectomix"].get(desc=config["connectivity_kinds"],
                                                       extension=".npy",
                                                       suffix="permutations",
                                                       return_type="filename")
    perm_files = apply_nonbids_filter("analysis",
                         config["analysis_label"],
                         perm_files)
    perm_files = apply_nonbids_filter("method",
                                      config["method"],
                                      perm_files)
    
    if len(perm_files) > 1:
        raise ValueError(f"Too many permutation files associated with analysis {config['analysis_label']}: {perm_files}. This should not happen, maybe a bug?")
    elif len(perm_files) == 1:
        perm_file = perm_files[0]
        perm_data = np.load(perm_file)
        print(f"Loading {perm_data.shape[0]} pre-existing permutations from {perm_file}")
    else:
        # Note: if we compare task, then the task entity must disappear in the path, so we make it optional in the path_patterns
        perm_file = layout.derivatives["connectomix"].build_path({**entities,
                                                          "analysis_label": config["analysis_label"],
                                                          "method": config["method"],
                                                          },
                                                     path_patterns=["group/{analysis_label}/permutations/group_[ses-{session}_][run-{run}_][task-{task}]_space-{space}_method-{method}_desc-{desc}_analysis-{analysis_label}_permutations.npy"],
                                                     validate=False)
        ensure_directory(perm_file)
        # If nothing has to be loaded, then initiate the null distribution with the observed values
        perm_data = np.array([list(observed_stats.values())])  # Size is (1,2) and order is max followed by min
    
    # Run the permutations until goal is reached
    print(f"Running permutations (target is {n_permutations} permutations)...", end="", flush=True)
    while perm_data.shape[0] <= n_permutations:
        print(".", end="", flush=True)
        if analysis_type in ["independent", "paired"]:
            group1_data = group_data[0]
            group2_data = group_data[1]
            if analysis_type == "independent":
                permutation_type = "independent"
            elif analysis_type == "paired":
                permutation_type = "samples"
            perm_test = permutation_test((group1_data, group2_data),
                                                          stat_func,
                                                          vectorized=False,
                                                          n_resamples=1,
                                                          permutation_type=permutation_type)
            permuted_t_scores = perm_test.null_distribution
            
        elif analysis_type == "regression":
            permuted_t_scores, _ = regression_analysis(group_data, design_matrix, permutate=True)
            
        null_data = np.array([np.nanmax(permuted_t_scores), np.nanmin(permuted_t_scores)])
        perm_data = np.vstack((perm_data, null_data.reshape(1, -1)))
    
        # Save to file
        np.save(perm_file, perm_data)
        
    print(".")
    print("Permutations computed.")
    return perm_data.reshape([-1,1])[0:], perm_data.reshape([-1,1])[1:]  # Returning all maxima and all minima


# Regression analysis of each connectivity value with a covariate, with optionnal confounds and optional permuted columns
def regression_analysis(group_data, design_matrix, permutate=False):
    """
    Performs regression analysis on symmetric connectivity matrices using vectorization.
    Assumes the covariate is the first column of the design matrix and optionally permutes it.
    
    Parameters:
    - group_data: A numpy array of shape (n_subjects, n_nodes, n_nodes), where each entry is a symmetric connectivity matrix.
    - design_matrix: A pandas DataFrame used as the design matrix for the regression.
    - permutate: A boolean indicating whether to shuffle the covariate before performing the regression.

    Returns:
    - t_values_matrix: A symmetric matrix of t-values for the covariate, with shape (n_nodes, n_nodes).
    - p_values_matrix: A symmetric matrix of p-values for the covariate, with shape (n_nodes, n_nodes).
    """
    
    # Get the number of subjects, nodes from group_data
    group_data = np.array(group_data)
    n_subjects, n_nodes, _ = group_data.shape

    # Extract name of columns to permute
    covariable_to_permute = design_matrix.columns[0]

    # Since we add a constant in the design matrix, we must de-mean the columns of the design matrix
    design_matrix = design_matrix.apply(lambda x: x - x.mean(), axis=0)

    # Extract the covariate (first column of design matrix) and other covariates
    X = add_constant(design_matrix)  # Add constant for the intercept

    # If permutate is True, shuffle the first column (covariate) of the design matrix
    if permutate:
        X[covariable_to_permute] = np.random.permutation(X[covariable_to_permute])

    # Vectorize the symmetric connectivity matrices (extract upper triangular part)
    vec_group_data = np.array([sym_matrix_to_vec(matrix) for matrix in group_data])

    # Get the number of unique connections (upper triangular part)
    n_connections = vec_group_data.shape[1]

    # Initialize arrays to store t-values and p-values for the vectorized form
    t_values_vec = np.zeros(n_connections)
    p_values_vec = np.zeros(n_connections)

    # Run the regression for each unique connection
    for idx in range(n_connections):
        # Connectivity values (y) for this connection across subjects
        y = vec_group_data[:, idx]

        # Fit the OLS model
        model = OLS(y, X).fit()

        # Extract t-value and p-value for the covariate (first column)
        t_values_vec[idx] = model.tvalues[covariable_to_permute]
        p_values_vec[idx] = model.pvalues[covariable_to_permute]

    # Convert the vectorized t-values and p-values back to symmetric matrices
    t_values_matrix = vec_to_sym_matrix(t_values_vec)
    p_values_matrix = vec_to_sym_matrix(p_values_vec)

    return t_values_matrix, p_values_matrix


# Define a function to compute the difference in connectivity between the two groups
# Todo: adapt this for paired tests
def stat_func(x, y):
    """
    Function defining the statistics to compute for the permutation-based analysis.
    Essentially calls ttest_ind(x, y).

    Parameters
    ----------
    x : as in ttest_ind(x, y)
    y : as in ttest_ind(x, y)

    Returns
    -------
    t_stat : float
        t-statistics, as computed from ttest_ind(x, y).

    """
    from scipy.stats import ttest_ind
    # Compute the t-statistic between two independent groups
    t_stat, _ = ttest_ind(x, y)
    return t_stat


# MAIN

# Define the autonomous mode, to guess paths and parameters
def autonomous_mode(run=False):
    """ Function to automatically guess the analysis paths and settings. """
    
    current_dir = Path.cwd()

    # Step 1: Find BIDS directory (bids_dir)
    if (current_dir / "dataset_description.json").exists():
        bids_dir = current_dir
    elif (current_dir / "rawdata" / "dataset_description.json").exists():
        bids_dir = current_dir / "rawdata"
    else:
        raise FileNotFoundError("Could not find 'dataset_description.json'. Ensure the current directory or 'rawdata' folder contains it.")

    # Step 2: Find derivatives directory and fMRIPrep directory
    derivatives_dir = current_dir / "derivatives"
    if not derivatives_dir.exists():
        raise FileNotFoundError("The 'derivatives' folder was not found. Ensure the folder exists in the current directory.")
    
    # Look for the fMRIPrep folder in derivatives
    fmriprep_folders = [f for f in derivatives_dir.iterdir() if f.is_dir() and f.name.lower().startswith("fmriprep")]
    
    if len(fmriprep_folders) == 1:
        fmriprep_dir = fmriprep_folders[0]
    elif len(fmriprep_folders) > 1:
        raise FileNotFoundError("Multiple 'fMRIPrep' directories found in 'derivatives'. Please resolve this ambiguity.")
    else:
        raise FileNotFoundError("No 'fMRIPrep' directory found in 'derivatives'.")

    # Step 3: Check if a "connectomix" folder already exists in derivatives
    connectomix_folder = [f for f in derivatives_dir.iterdir() if f.is_dir() and f.name.lower().startswith("connectomix")]
    
    if len(connectomix_folder) == 0:
        # No connectomix folder found, assume participant-level analysis
        connectomix_folder = Path(derivatives_dir) / "connectomix"
        analysis_level = "participant"
        
    elif len(connectomix_folder) == 1:
        # Connectomix folder exists and is unique, checking if something has already been run at participant-level
        connectomix_folder = connectomix_folder[0]
        layout = BIDSLayout(bids_dir, derivatives=[connectomix_folder])
        if len(layout.derivatives["connectomix"].get_subjects()) == 0:
            print("No participant-level result detected, assuming participant-level analysis")
            analysis_level = "participant"
        else:
            print(f"Detected participant-level results for subjects {layout.derivatives['connectomix'].get_subjects()}, assuming group-level analysis")
            analysis_level = "group"
        
    else:
        raise ValueError(f"Several connectomix directories where found ({connectomix_folder}). Please resolve this ambiguity.")
    
    
    # Step 4: Call the main function with guessed paths and settings
    if run:
        print("... and now launching the analysis!")
        if analysis_level == "participant":
            participant_level_analysis(bids_dir, connectomix_folder, {"fmriprep": fmriprep_dir}, {})
        elif analysis_level == "group":
            group_level_analysis(bids_dir, connectomix_folder, {})
    else:
        if analysis_level == "participant":
            create_participant_level_default_config_file(bids_dir, connectomix_folder, fmriprep_dir)
        elif analysis_level == "group":
            create_group_level_default_config_file(bids_dir, connectomix_folder)

        cmd = f"python connectomix.py {bids_dir} {connectomix_folder} {analysis_level} --derivatives fmriprep={fmriprep_dir}"
        print(f"Autonomous mode suggests the following command:\n{cmd}")
        print("If you are happy with this configuration, run this command or simply relaunch the autonomous mode add the --run flag.")



# Participant-level analysis
def participant_level_analysis(bids_dir, output_dir, derivatives, config):
    """
    Main function to run the participant analysis

    Parameters
    ----------
    bids_dir : str or Path
        Path to bids_dir.
    output_dir : str or Path
        Path to connectomix derivatives.
    derivatives : dict
        Paths to data preprocessed with fMRIPrep and, optionally, fmripost-aroma: derivatives["fmriprep"]="/path/to/fmriprep", etc.
    config : dict or str or Path
        Configuration dict or path to configuration file (can be a .json or .yaml or .yml).

    Returns
    -------
    None.

    """
    # Print version information
    print(f"Running connectomix (Participant-level) version {__version__}")

    # Create BIDSLayout with pipeline and other derivatives
    layout = setup_layout(bids_dir, output_dir, derivatives)
    
    # Load and backup the configuration file
    config = setup_config(layout, config, "participant")

    # Select all files needed for analysis
    func_files, json_files, confound_files = get_files_for_analysis(layout, config)
    print(f"Found {len(func_files)} functional files:")
    [print(os.path.basename(fn)) for fn in func_files]

    # Resample all functional files to the reference image
    resampled_files = resample_to_reference(layout, func_files, config)
    print("All functional files resampled to match the reference image.")

    denoised_files = denoise_fmri_data(layout, resampled_files, confound_files, json_files, config)
    print("Denoising finished.")

    # TODO: replace "ica" by "canica
    # Compute CanICA components if necessary and store it in the methods options
    config = compute_canica_components(layout, denoised_files, config) if config["method"] == "ica" else config
    
    print(f"Selected method for connectivity analysis: {config['method']}")    

    # Iterate through each functional file
    for (func_file, json_file) in zip(denoised_files, json_files):
        # Print status
        entities = layout.parse_file_entities(func_file)
        print(f"Processing subject {entities['subject']}")
        
        # Generate the BIDS-compliant filename for the timeseries and save
        # TODO: add label to output path. This requires sont change in the structure here...
        timeseries_path = layout.derivatives["connectomix"].build_path(entities,
                                                  path_patterns=["sub-{subject}/[ses-{session}/]sub-{subject}_[ses-{session}_][run-{run}_]task-{task}_space-{space}_method-%s_timeseries.npy" % config["method"]],
                                                  validate=False)
        ensure_directory(timeseries_path)
        
        # Extract timeseries and save
        timeseries_list, labels = extract_timeseries(str(func_file),
                                                get_repetition_time(json_file),
                                                config)
        np.save(timeseries_path, timeseries_list)
        
        if config["method"] == "roiToVoxel":
            roi_to_voxel_participant_analysis(layout, func_file, json_file, timeseries_list, labels, config)
        else:
            roi_to_roi_participant_analysis(layout, func_file, json_file, timeseries_list, labels, config)
        
    print("Participant-level analysis completed.")


# Group-level analysis
def group_level_analysis(bids_dir, output_dir, config):
    """
    Main function to launch group-level analysis.

    Parameters
    ----------
    bids_dir : str or Path
        Path to bids_dir.
    output_dir : str or Path
        Path to connectomix derivatives.
    config : dict or str or Path
        Configuration or path to configuration (can be a .json or .yaml or .yml).

    Returns
    -------
    None.

    """
    # Print version information
    print(f"Running connectomix (Group-level) version {__version__}")

    # Create BIDSLayout with pipeline and other derivatives
    layout = setup_layout(bids_dir, output_dir)
    
    # Load and backup the configuration file
    config = setup_config(layout, config, "group")

    if config["method"] == "roiToVoxel":
        roi_to_voxel_group_analysis(layout, config)
    else:
        roi_to_roi_group_analysis(layout, config)

    print("Group-level analysis completed.")


# Main function with subcommands for participant and group analysis
def main():
    """
    Main function to launch the software. Ir reads arguments from sys.argv, which is filled automatically when calling the script from command line.

    Returns
    -------
    None.

    """
    
    parser = argparse.ArgumentParser(description="Connectomix: Functional Connectivity from fMRIPrep outputs using BIDS structure")
    
    # Define the autonomous flag
    parser.add_argument("--autonomous", action="store_true", help="Run the script in autonomous mode, guessing paths and settings.")
    
    # Define the run flag
    parser.add_argument("--run", action="store_true", help="Run the analysis based on what the autonomous mode found.")
    
    # Define positional arguments for bids_dir, derivatives_dir, and analysis_level
    parser.add_argument("bids_dir", nargs="?", type=str, help="BIDS root directory containing the dataset.")
    parser.add_argument("output_dir", nargs="?", type=str, help="Directory where to store the outputs.")
    parser.add_argument("analysis_level", nargs="?", choices=["participant", "group"], help="Analysis level: either 'participant' or 'group'.")
    
    # Define optional arguments that apply to both analysis levels
    parser.add_argument("-d", "--derivatives", nargs="+",
                        help="Specify pre-computed derivatives as 'key=value' pairs (e.g., -d fmriprep=/path/to/fmriprep fmripost-aroma=/path/to/fmripost-aroma).")
    parser.add_argument("-c", "--config", type=str, help="Path to the configuration file.")
    parser.add_argument("-p", "--participant_label", type=str, help="Participant label to process (e.g., 'sub-01').")
    parser.add_argument("--helper", help="Helper function to write default configuration files.", action="store_true")

    args = parser.parse_args()

    # Convert the list of "key=value" pairs to a dictionary
    derivatives = parse_derivatives(args.derivatives)
    
    # Run autonomous mode if flag is used
    if args.autonomous:
        autonomous_mode(run=args.run)
    else:
        # Set derivatives to default values if unset by user
        derivatives["fmriprep"] = derivatives.get("fmriprep", Path(args.bids_dir) / "derivatives" / "fmriprep")
        derivatives["fmripost-aroma"] = derivatives.get("fmripost-aroma", Path(args.bids_dir) / "derivatives" / "fmripost-aroma")
        
        # Run the appropriate analysis level
        if args.analysis_level == "participant":
            
            # Check if fMRIPrep directory exists
            if not Path(derivatives["fmriprep"]).exists():
                raise FileNotFoundError(f"fMRIPrep directory {derivatives['fmriprep']} not found. Use '--derivatives fmriprep=/path/to/fmriprep' to specify path manually.")
            
            # First check if only helper function must be called
            if args.helper:
                create_participant_level_default_config_file(args.bids_dir, args.output_dir, derivatives["fmriprep"])
            else:
                participant_level_analysis(args.bids_dir, args.output_dir, derivatives, args.config)
        elif args.analysis_level == "group":
            # First check if only helper function must be called
            if args.helper:
                create_group_level_default_config_file(args.bids_dir, args.output_dir)
            else:
                group_level_analysis(args.bids_dir, args.output_dir, args.config)

if __name__ == "__main__":
    main()
