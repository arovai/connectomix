import matplotlib.pyplot as plt
import importlib.resources

from connectomix.core.core import participant_level_pipeline, group_level_pipeline
from connectomix.tests.paths import bids_dir, fmriprep_dir, output_dir

example_seeds_for_seedToSeed = str(importlib.resources.files("connectomix.tests.data").joinpath("example_seeds_for_seedToSeed.tsv"))

method = "seedToSeed"

# Participant
participant_level_pipeline(bids_dir,
                           output_dir,
                           derivatives={"fmriprep": fmriprep_dir},
                           config={"method": method,
                                   "custom_seeds_name": "test",
                                   "seeds_file": example_seeds_for_seedToSeed})

# Group
## One-sample t-test
group_level_pipeline(bids_dir,
                     output_dir,
                     config={"method": method,
                             "custom_seeds_name": "test",
                             "seeds_file": example_seeds_for_seedToSeed,
                             "analysis_name": "testMeanEffect",
                             "contrast": "intercept",
                             "fdr_alpha": 0.5,
                             "fwe_alpha":  0.5,
                             "n_permutations": 10,
                             "thresholding_strategies": ["uncorrected",
                                                         "fdr",
                                                         "fwe"]})
plt.close('all')