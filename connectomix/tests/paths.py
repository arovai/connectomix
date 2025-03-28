import os

from connectomix.version import __version__

# ------ Set-up for ds005699 - 4 subjects, two groups, one task (no session or run)
ds = "ds005699"

# laptop paths

bids_dir = os.path.join("/rawdata", ds)
fmriprep_dir = os.path.join("/derivatives", ds, "fmriprep")
output_dir = os.path.join("/derivatives", ds, f"connectomix-{__version__}-tests")

# tower paths

# bids_dir = os.path.join("/data/openneuro", ds)
# fmriprep_dir = os.path.join("/data/openneuro", ds, "derivatives", "fmriprep")
# output_dir = os.path.join("/data/openneuro", ds, "derivatives", f"connectomix-{__version__}-tests")
