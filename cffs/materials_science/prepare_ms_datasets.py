"""Materials science dataset preparation

Script which saves multiple materials science dataset in a format suitable for the MS pipeline.

Usage: python prepare_ms_datasets.py --help
"""


import argparse
import pathlib

import tqdm

from cffs.utilities import data_utility
from cffs.materials_science import ms_data_utility


MS_DATA_PATHS = {
    'sampled_merged_2400': pathlib.Path(
        'C:/MyData/Versetzungsdaten/Voxel_Data/sampled_merged_last_voxel_data_size2400_order2_speedUp2.csv'),
    'sampled_merged_2400_strain': pathlib.Path(
        'C:/MyData/Versetzungsdaten/Balduin_config41/sampled_merged_last_voxel_data_size2400_order2_speedUp2_strain_rate.csv'),
    'sampled_voxel_2400': pathlib.Path(
        'C:/MyData/Versetzungsdaten/Voxel_Data/sampled_voxel_data_size2400_order2_speedUp2.csv'),
    'sampled_voxel_2400_strain': pathlib.Path(
        'C:/MyData/Versetzungsdaten/Balduin_config41/sampled_voxel_data_size2400_order2_speedUp2_strain_rate.csv')
}


def prepare_ms_datasets(data_dir: pathlib.Path) -> None:
    if not data_dir.is_dir():
        print('Directory does not exist. We create it.')
        data_dir.mkdir(parents=True)
    if len(list(data_dir.glob('*'))) > 0:
        print('Data directory is not empty. Files might be overwritten, but not deleted.')
    for dataset_name, data_path in tqdm.tqdm(MS_DATA_PATHS.items()):
        if 'sampled_merged' in data_path.stem:
            loading_func = ms_data_utility.prepare_sampled_merged_data
        else:
            loading_func = ms_data_utility.prepare_sampled_voxel_data
        dataset = loading_func(data_path, delta_steps=0, subset='none')
        prediction_scenario = ms_data_utility.predict_voxel_data_absolute(
            dataset=dataset, reaction_type='glissile', add_aggregates=True)
        data_utility.save_dataset(X=prediction_scenario['dataset'][prediction_scenario['features']],
                                  y=prediction_scenario['dataset'][prediction_scenario['target']],
                                  dataset_name=dataset_name + '_absolute_glissile', directory=data_dir)
        dataset = loading_func(data_path, delta_steps=20, subset='complete')
        prediction_scenario = ms_data_utility.predict_voxel_data_relative(
            dataset=dataset, reaction_type='glissile', add_aggregates=True)
        data_utility.save_dataset(X=prediction_scenario['dataset'][prediction_scenario['features']],
                                  y=prediction_scenario['dataset'][prediction_scenario['target']],
                                  dataset_name=dataset_name + '_delta20_glissile', directory=data_dir)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Prepares multiple material science datasets for the MS pipeline and stores them ' +
        'in the specified directory.', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-d', '--directory', type=str, default='data/ms/', help='Output directory for data.')
    prepare_ms_datasets(data_dir=pathlib.Path(parser.parse_args().directory))
    print('Datasets prepared and saved.')