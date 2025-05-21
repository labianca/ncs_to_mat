
import os
import os.path as op
import time
from datetime import datetime


def sanitize_for_matlab(d):
    """Convert dict values to MATLAB-compatible format, ensuring lists of strings become cell arrays."""
    import numpy as np

    clean = {}
    for k, v in d.items():
        k_clean = k.replace('µ', 'u')  # Clean field names if needed

        if k.endswith('_dt'):
            continue  # Skip datetime fields

        # Convert datetime to ISO string
        if isinstance(v, datetime):
            clean[k_clean] = v.isoformat()

        # Convert list of strings (or None) to cell array
        elif isinstance(v, list):
            converted = []
            for item in v:
                if item is None:
                    converted.append('')
                else:
                    converted.append(item)
            clean[k_clean] = np.array(converted, dtype=object)[:, None]

        # Convert None to empty string
        elif v is None:
            clean[k_clean] = ''

        # Leave other types (e.g., string) unchanged
        else:
            clean[k_clean] = v

    return clean



def format_headers(all_headers):
    # Define header field categories
    static_header_fields = [
        'FileType', 'FileVersion', 'SessionUUID', 'TimeClosed', 'TimeClosed_dt',
        'ProbeName', 'RecordSize', 'ApplicationName',
        'AcquisitionSystem', 'ADMaxValue', 'NumADChannels', 'InputInverted',
        'DSPLowCutFilterEnabled', 'DspLowCutFrequency', 'DspLowCutNumTaps',
        'DspLowCutFilterType', 'DSPHighCutFilterEnabled', 'DspHighCutNumTaps',
        'DspHighCutFilterType', 'DspDelayCompensation', 'DspFilterDelay_µs'
    ]

    varying_header_fields = [
        'TimeCreated', 'TimeOpened_dt', 'FileName', 'FileUUID', 'OriginalFileName', 'AcqEntName', 'ADChannel',
        'ReferenceChannel', 'SamplingFrequency', 'ADBitVolts', 'InputRange',
        'DspHighCutFrequency'
    ]

    all_fields = static_header_fields + varying_header_fields
    for hdr in all_headers:
        for fld in hdr.keys():
            if fld not in all_fields:
                print(f'{fld} not in recorded fields.')


    # make sure we have the same fields across headers
    common_fields = list(all_headers[0].keys())

    for header_idx, header in enumerate(all_headers):
        flds = list(header.keys())
        same = (len(flds) == len(common_fields)
                and all([fld in common_fields for fld in flds]))
        if not same:
            print(f'Header with index {header_idx} has more fields...')

    # Construct output structure
    header_struct = {}

    # Fill in static fields
    for field in common_fields:
        # do not export the _dt ending fields
        if field.endswith('_dt'):
            continue

        if field in static_header_fields:
            first_value = all_headers[0].get(field)
            if all(header.get(field) == first_value for header in all_headers):
                header_struct[field] = first_value
            else:
                varying_header_fields.append(field)

        if field in varying_header_fields:
            header_struct[field] = [header.get(field) for header in all_headers]

    header_struct = sanitize_for_matlab(header_struct)
    return header_struct


def csc_numsort(files):
    """Sort CSCxxx.ncs files by the numerical value if xxx is a number."""
    import numpy as np

    num_names, rest_names = list(), list()
    numbers = list()

    for file in files:
        num_chan = False
        if file.endswith('.ncs'):
            if file.startswith('CSC'):
                fbase = file.removesuffix('.ncs').removeprefix('CSC')
                num_chan = fbase.isdigit()

        if num_chan:
            num_names.append(file)
            numbers.append(int(fbase))
        else:
            rest_names.append(file)

    rest_names.sort()

    # sort the numeric files:
    numbers = np.array(numbers)
    sorting = np.argsort(numbers)

    sorted_num_names = [num_names[idx] for idx in sorting]

    return sorted_num_names + rest_names


def convert_recording(read_dir, write_dir, gui=None, rescale_data=True,
                      ignore_inverted=True):
    """
    Convert Neuralynx recording files to MATLAB format.

    Parameters
    ----------
    read_dir: str
        Directory containing the input files.
    write_dir: str
        Directory to save the output files.
    """
    import numpy as np
    from scipy.io import savemat
    import humanize
    from pylabianca.neuralynx_io import read_header
    from pylabianca.io import read_events_neuralynx
    from pylabianca.neuralynx_io import load_ncs

    try:
        import h5py
        use_scipy = False
        log_update('Found hdf5storage library, it will be used instead of '
                   'scipy to save data files.', gui=gui)
    except ImportError:
        use_scipy = True
        log_update('Could not find the hdf5storage library, scipy.savemat will'
                   ' be used instead to save data files. This can be '
                   'significantly slower.', gui=gui)

    # Check if the output directory exists, if not create it
    if not os.path.exists(write_dir):
        os.makedirs(write_dir)

    # Set your data directory
    files = os.listdir(read_dir)
    files = csc_numsort(files)

    # Filter .ncs files
    ncs_files = [f for f in files if f.endswith('.ncs')]
    n_files = len(ncs_files)
    progress_update(0, total_steps=n_files, gui=gui)

    log_update('Checking file sizes', gui=gui)
    file_sizes = [os.path.getsize(op.join(read_dir, f)) for f in ncs_files]
    total_size = sum(file_sizes)
    estimated_time_per_byte = 0.0
    processed_bytes = 0.0
    elapsed_time = 0.0
    if gui is not None:
        gui.update_estimated(estimated_time_per_byte)

    # Processing events
    log_update('Reading events', gui=gui)
    nev_files = [f for f in files if f.endswith('.nev')]
    if not len(nev_files) == 1:
        raise RuntimeError('The recording has to have exactly one events *.nev '
                        f'file, found {len(nev_files)}.')

    events = read_events_neuralynx(
        read_dir, events_file=nev_files[0], format='mne')
    events = np.delete(events, 1, axis=1)

    log_update(f'Saving events', gui=gui)
    savemat(op.join(write_dir, 'events.mat'), {'events': events})

    all_headers = list()
    scaling_applied = list()
    inversion_applied = list()
    timestamps_store = list()
    timestamps_mapping = list()

    mat_files = list()
    previous_timestamp = None

    mapping_from_file = np.zeros((n_files, 1), dtype=int)
    has_data = np.zeros((n_files, 1), dtype=bool)

    log_update(f'Found {n_files} .ncs files. Processing:', gui=gui)
    start_time = time.time()

    for file_idx, file in enumerate(ncs_files):

        log_update(f'Reading ncs file: {file}', gui=gui)
        data = load_ncs(op.join(read_dir, file), load_time=False,
                        rescale_data=rescale_data)

        if len(data['data']) == 0:
            has_data[file_idx, 0] = False
            mat_files.append('IGNORED')
            all_headers.append(data['header'])
            scaling_applied.append(False)
            inversion_applied.append(False)
            log_update(f'File {file} is empty. Skipping.', gui=gui)
            processed_bytes += file_sizes[file_idx]
            continue
        else:
            has_data[file_idx, 0] = True

        timestartOffset = data['timestamp'][0] - (1e6 / data['sampling_rate'])

        if bool(data['header']['InputInverted']) and not ignore_inverted:
            data['data'] *= -1
            did_invert = True
        else:
            did_invert = False

        # process timestamps
        if previous_timestamp is None:
            new_timestamp = True

            # make sure continuous timestamps:
            expected_diff = int(512 * (1e6 / data['sampling_rate']))
            timestamp_diffs = np.unique(np.diff(data['timestamp'])).astype(int)
            is_continuous = ((np.abs(timestamp_diffs - expected_diff)
                             < expected_diff).all())

            if not is_continuous:
                raise RuntimeError('The recording is not continuous (there '
                                    'were pauses in the recording)!')
        else:
            # check if new timestamp
            new_timestamp = not (data['timestamp'].shape[0]
                                 == previous_timestamp.shape[0])
            if not new_timestamp:
                new_timestamp = (not (data['timestamp']
                                      == previous_timestamp).all())

        if new_timestamp:
            if len(timestamps_mapping) > 0:
                timestamps_mapping[-1] = np.array(timestamps_mapping[-1]) + 1
            timestamps_store.append(data['timestamp'])
            timestamps_mapping.append([file_idx])
            previous_timestamp = data['timestamp']
        else:
            timestamps_mapping[-1].append(file_idx)
        mapping_from_file[file_idx, 0] = len(timestamps_mapping)

        # save to .mat
        output_file = file.replace('.ncs', '.mat')
        output_filepath = op.join(write_dir, output_file)
        log_update(f'Writing mat file: {output_file}', gui=gui)

        if use_scipy:
            savemat(output_filepath,
                    {'data': data['data'], 'timestartOffset': timestartOffset},
                    do_compression=True)
        else:
            write_matlab_hdf5(data['data'], timestartOffset, output_filepath)

        # update multi-file variables (for the aggregated header)
        mat_files.append(output_file)
        all_headers.append(data['header'])
        scaling_applied.append(rescale_data)
        inversion_applied.append(did_invert)

        # update estimated time
        processed_bytes += file_sizes[file_idx]
        if gui is not None:
            elapsed_time = time.time() - start_time
            estimated_time_per_byte = elapsed_time / processed_bytes
            estimated_time = estimated_time_per_byte * (total_size - processed_bytes)
            gui.update_estimated(estimated_time)

        progress_update(file_idx + 1, total_steps=n_files, gui=gui)

    log_update('Saving unique timestamp arrays', gui=gui)
    mat_files = np.array(mat_files, dtype=object)[:, None]
    timestamps_mapping[-1] = np.array(timestamps_mapping[-1]) + 1

    mapping = np.empty(len(timestamps_mapping), dtype=object)
    mapping[:] = timestamps_mapping
    mapping = mapping[:, None]

    timestamps = np.empty(len(timestamps_store), dtype=object)
    timestamps[:] = timestamps_store
    timestamps = timestamps[:, None]

    savemat(
        op.join(write_dir, 'timestamps.mat'),
        {'files': mat_files, 'timestamps': timestamps,
         'mapping': mapping_from_file, 'mapping_reverse': mapping}
    )

    log_update('Processing headers', gui=gui)
    header_struct = format_headers(all_headers)
    header_struct['export_version'] = '0.1'
    header_struct['data_files'] = mat_files
    header_struct['has_data'] = has_data
    header_struct['timestamp_file'] = 'timestamps.mat'
    header_struct['event_file'] = 'events.mat'
    header_struct['scaling_applied'] = scaling_applied
    header_struct['inversion_applied'] = inversion_applied

    # Save to .mat file
    log_update('Saving headers', gui=gui)
    output_file = op.join(write_dir, 'ncs_headers.mat')
    savemat(output_file, {'ncs_headers': header_struct})

    elapsed_time = time.time() - start_time

    # print how long it took
    log_update("Done!", gui=gui)
    log_update(
        f"Elapsed time: {humanize.precisedelta(elapsed_time)}",
        gui=gui
    )


def progress_update(step_idx, total_steps, gui):
    if gui is not None:
        # Update the GUI progress bar
        gui.update_file_progress(step_idx, total_steps)

def log_update(txt, gui=None):
    if gui is not None:
        gui.log(txt)
    else:
        print(txt)

def write_matlab_hdf5(data, timestartOffset, filepath):
    import hdf5storage

    hdf5storage.savemat(
        filepath,
        {'data': data, 'timestartOffset': timestartOffset},
        format='7.3',
        store_python_metadata=False,
        oned_as='column'
    )
