# -*- coding: utf-8 -*-

from collections.abc import MutableMapping
from configparser import ConfigParser, SectionProxy
from os import path
from pathlib import Path
from typing import Any, Optional, Union, Iterable, Tuple, List, Mapping, Iterator

from odev.utils.os import mkdir


ConfigSectionType = MutableMapping[str, str]
ConfigType = MutableMapping[str, ConfigSectionType]


class ConfigManager(MutableMapping):
    '''
    Light wrapper around configparser to write and retrieve configuration
    saved on disk.
    '''

    ODEV_CONFIG_DIR: str = str(Path.home() / '.config' / 'odev')

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

    parser: ConfigParser = {}
    '''
    Config parser implementation
    '''

    def __init__(self, name: str, auto_save: bool = True):
        '''
        Light wrapper around configparser to write and retrieve configuration
        saved on disk.
        '''

        self.name: str = name
        self.path: str = path.join(self.ODEV_CONFIG_DIR, f'{self.name}.cfg')
        self.parser: ConfigParser = ConfigParser()
        self.auto_save: bool = auto_save

        if not path.isdir(self.ODEV_CONFIG_DIR):
            mkdir(self.ODEV_CONFIG_DIR)

        if not path.isfile(self.path):
            open(self.path, 'a').close()

        self.load()

    def to_dict(self) -> ConfigType:
        return {section.name: dict(section) for section in self.parser.values() if section}

    def load(self) -> ConfigType:
        '''
        Load the content of an existing config file.
        :return: A dict containing the config read from file
        '''

        self.parser.read(self.path)
        return self.parser

    def save(self, *args: Union[ConfigType, Iterable[Tuple[str, ConfigSectionType]]], overwrite: bool = False, **kwargs: ConfigSectionType):
        '''
        Save the configuration file, optionally with the additional provided data.
        :param args: values for the config either as a mapping or as an iterable of tuples.
        :param kwargs: values for the config with sections as keyword arguments.
        :param overwrite: Replace the contents of the config file with the provided ones.
            Defaults to False.
        :return: The current config data
        '''

        if overwrite:
            self.clear()

        sections_vals: ConfigType = self.to_dict()
        sections_vals.update(dict(*args, **kwargs))

        self.parser.read_dict(sections_vals)

        with open(self.path, 'w') as file:
            self.parser.write(file)

        return self.parser

    def clear(self) -> ConfigType:
        self.parser.clear()
        return self.parser

    def set(self, section: str, key: str, value: Any) -> ConfigType:
        '''
        Set the value for a given key in a specific section
        '''

        if section not in self.parser:
            self.parser.add_section(section)
        self.parser.set(section, key, str(value))
        if self.auto_save:
            self.save()
        return self.parser

    # NOTE: signature doesn't match MutableMapping because we get an option, not a section
    def get(self, section: str, key: str, default: Any = None) -> Any:
        '''
        Get a value for a given key in a specific section,
        or a default value if not set
        '''

        return self.parser.get(section, key, fallback=default)

    def delete(self, section: str, name: Optional[str] = None):
        '''
        Removes an option or a section from the config file.
        '''

        if section in self.parser:
            if name:
                self.parser.remove_option(section, name)
            else:
                self.parser.remove_section(section)

        if self.auto_save:
            self.save()
        return self.parser

    def __getitem__(self, section: str) -> SectionProxy:
        if section not in self.parser:
            self.parser.add_section(section)
        return self.parser[section]

    def __setitem__(self, section: str, value: Mapping[str, str]) -> None:
        self.parser.__setitem__(section, value)

    def __delitem__(self, section: str) -> None:
        self.parser.__delitem__(section)

    def sections(self) -> List[str]:
        """Return a list of section names, excluding DEFAULT"""
        return self.parser.sections()

    def __len__(self) -> int:
        """Sections in the config file, excluding DEFAULT"""
        return len(self.sections())

    def __iter__(self) -> Iterator[str]:
        """Iterate over sections, excluding DEFAULT"""
        return iter(self.sections())

    def __enter__(self):
        self.auto_save = False
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not any((exc_type, exc_val, exc_tb)):
            self.save()
            self.auto_save = True
