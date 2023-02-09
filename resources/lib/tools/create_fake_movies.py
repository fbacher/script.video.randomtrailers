#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Created on 7/21/22

@author: Frank Feuerbacher
"""
import io
import os
from typing import List

if __name__ == '__main__':
    fake_movie_to_link_to: str = '/scratch/fake_movies/real/dummy_movie.mkv'
    fake_movie_directory: str = '/scratch/fake_movies/fake'
    simulated_file_names: str = \
        '/home/fbacher/.kodi/userdata/addon_data/script.video.randomtrailers/simulated_movie_paths'
    try:
        with io.open(simulated_file_names, mode='rt', newline=None,
                     encoding='utf-8') as simulated_paths:
            fake_movie_names: List[str] = simulated_paths.readlines()
            fake_movie_name: str
            for fake_movie_name in fake_movie_names:
                print(f'fake movie name: {fake_movie_name}')
                if fake_movie_name is None:
                    break
                fake_movie_name = fake_movie_name.replace("\n", "")
                fake_path: str = f'{fake_movie_directory}/{fake_movie_name}'
                print(fake_path)
                try:
                    if not os.path.isfile(fake_path):
                        os.symlink(fake_movie_to_link_to, fake_path)
                except Exception as e:
                    print(f'exception: {fake_path}')

    except Exception as e:
        exit()