# -*- coding: utf-8 -*-

from configparser import ConfigParser
from os import path
from pathlib import Path
from typing import Any, Dict

from odev.utils.os import mkdir


class ConfigManager:
    '''
    Light wrapper around configparser to write and retrieve configuration
    saved on disk.
    '''

    name: str
    '''
    Name of this config manager, also serves as the name
    of the file to save configuration in
    '''

    path: str
    '''
    Path to the file containing configuration options,
    inferred from the name
    '''

    config: Dict[str, Dict[str, str]] = {}
    '''
    Configuration options as saved to disk, grouped by sections
    :examples:
    >>> {
        'section_1': {
            'key_1': 'value_1',
            'key_2': 'value_2',
        }
    }
    '''

    parser: ConfigParser
    '''
    Config parser implementation
    '''

    def __init__(self, name: str):
        '''
        Light wrapper around configparser to write and retrieve configuration
        saved on disk.
        '''

        super().__init__()
        self.name = name
        directory = path.join(Path.home(), '.config', 'odev')
        self.path = path.join(directory, f'{self.name}.cfg')
        self.parser = ConfigParser()

        if not path.isdir(directory):
            mkdir(directory)

        if not path.isfile(self.path):
            open(self.path, 'a').close()

        self.load()

    def load(self) -> Dict[str, Dict[str, str]]:
        '''
        Load the content of an existing config file.
        :return: A dict containing the config read from file
        '''

        self.parser.read(self.path)
        self.config = {}

        for section in self.parser.sections():
            self.config[section] = {}

            for key in self.parser.options(section):
                self.config[section][key] = self.parser.get(section, key)

        return self.config

    def save(self, **vals: Dict[str, str]):
        '''
        Save a specific configuration to the filesystem.
        This overwrites the existing file.
        :return: The config that was written to file
        '''

        if not vals:
            vals = self.config

        with open(self.path, 'w') as file:
            for section, values in vals.items():
                if not self.parser.has_section(section):
                    self.parser.add_section(section)

                for key, value in values.items():
                    self.parser.set(section, key, value)

            self.parser.write(file)

        return self.load()

    def set(self, section: str, key: str, value: Any):
        '''
        Set the value for a given key in a specific section
        '''

        self.config[section] = self.config.get(section, {})
        self.config[section].update({key: str(value)})
        return self.save(**self.config)

    def get(self, section: str, key: str, default: Any = None):
        '''
        Get a value for a given key in a specific section,
        or a default value if not set
        '''

        return self.config.get(section, {}).get(key, default)

    def delete(self, section: str):
        '''
        Removes a section from the config file
        '''

        self.parser.remove_section(section)
        del self.config[section]
        return self.save(**self.config)
