#!/usr/bin/env python
import sys
import logging
import re
from itertools import izip_longest

from slugify import slugify_filename

logger = logging.getLogger(__name__)


class ImportFileHeaderLengthError(Exception):
    pass


class ImportFileHeaderContentError(Exception):
    pass


class OilLibraryCsvFile(object):
    ''' A specialized file reader for the OilLib and CustLib
        flat datafiles.
        - We will use universal newline support to designate
          a line of text.
        - Additionally, each line contains a number of fields
          separated by a tab ('\t').  In this way it attempts
          to represent tabular data.
        - The first line in the file contains a file format
          version number ('N.N'), followed by a date ('d/m/YY'),
          and finally the product ('adios').
        - The second line in the file contains a table header,
          where each field represents the "long" name of a
          tabular column.
        - The rest of the lines in the file contain table data.
    '''
    def __init__(self, name, field_delim='\t', ignore_version=False):
        '''
            :param name: The name of the oil library import file
            :type name: A path as a string or unicode

            :param field_delim='\t': The character to be used as a tabular
                                     field delimiter.
            :type field_delim: A string or unicode

            :param ignore_version=False: Ignore the exceptions generated by a
                                         failure to parse the version header
                                         in the file.
                                         Normally we want to simply fail in
                                         this case, but for diagnosing the
                                         content of new or unfamiliar import
                                         files, we can continue on in an
                                         attempt to build our object.
            :type ignore_version: Boolean
        '''
        self.name = name
        self.file_columns = None
        self.file_columns_lu = None
        self.num_columns = None

        self.fileobj = open(name, 'rU')
        self.field_delim = field_delim

        self.__version__ = self.readline()
        self._check_version_hdr(ignore_version)

        self._set_table_columns()

    def _check_version_hdr(self, ignore_version):
        '''
            Check that the file has a proper header.  Right now we are just
            checking for adios specific fields.
        '''
        if len(self.__version__) != 3:
            if ignore_version:
                # If we failed on header length, it is likely we have a
                # missing header.  If so, we probably read the column names
                # instead.  So we need to undo our readline() if we are
                # ignoring this.
                self.__version__ = None
                self.fileobj.seek(0)
            else:
                raise ImportFileHeaderLengthError('Bad file header: '
                                                  'did not find '
                                                  '3 fields for version!!')
        elif not self.__version__[-1].startswith('adios'):
            if ignore_version:
                # If we failed on header content, we probably have a bad
                # or unexpected header, but a header nonetheless.
                pass
            else:
                raise ImportFileHeaderContentError('Bad file header: '
                                                   'did not find '
                                                   'product field!!')

    def _set_table_columns(self):
        self.file_columns = self.readline()
        self.file_columns_lu = dict(zip(self.file_columns,
                                        range(len(self.file_columns))))
        self.num_columns = len(self.file_columns)

    def _parse_row(self, line):
        if line == '':
            # readline() returns empty string on EOF and '\n' for empty lines
            return None

        line = line.strip()
        if len(line) > 0:
            try:
                row = line.decode('utf-8')
            except Exception:
                # If we fail to encode in utf-8, then it is possible that
                # our file contains mac_roman characters of which some are
                # out-of-range.
                # This is probably about the best we can do to anticipate
                # our file contents.
                row = line.decode('mac_roman')

            row = row.encode('utf-8')
            row = (row.split(self.field_delim))
            row = [c.strip('"') for c in row]
            row = [c if len(c) > 0 else None for c in row]
        else:
            row = []
        return row

    def readline(self):
        return self._parse_row(self.fileobj.readline())

    def readlines(self):
        while True:
            line = self.readline()

            if line is None:
                break
            elif len(line) > 0:
                yield line

    def get_records(self):
        '''
            This is the API that the oil import processes expect
        '''
        for r in self.readlines():
            if len(r) < 10:
                logger.info('got record: {}'.format(r))

            r = [unicode(f, 'utf-8') if f is not None else f
                 for f in r]

            yield self.file_columns, r

    def rewind(self):
        self.fileobj.seek(0)
        first_line = self.readline()

        if (self.__version__ is not None and
                len(first_line) == len(self.__version__)):
            logger.debug('first line contains the version header')
            self.readline()
        elif len(first_line) == len(self.file_columns):
            # For tabular data, the number of data fields should be the same
            # as the column names, so this check will not be able to tell
            # if the column names are missing.
            # But at this point, we have already opened the file and
            # constructed our object and performed as many reasonable checks
            # as we can.  So we just try to be consistent with that.
            logger.debug('first line contains the file column names')
        else:
            raise ImportFileHeaderLengthError('Bad file header: '
                                              'should have found either '
                                              'the version or field names '
                                              'in the first row!!')

    def export(self, filename):
        self.rewind()

        file_out = open(filename, 'w')

        if self.__version__ is not None:
            logger.debug(self.field_delim.join(self.__version__))

            file_out.write(self.field_delim.join(self.__version__))
            file_out.write('\n')

        file_out.write(self.field_delim.join(self.file_columns))
        file_out.write('\n')

        for line in self.readlines():
            line = ['' if f is None else f
                    for f in line]

            sys.stderr.write('.')
            file_out.write(self.field_delim.join(line))
            file_out.write('\n')

        file_out.close()

    def __repr__(self):
        return ("<{}('{}')>".format(self.__class__.__name__, self.name))


class OilLibraryRecordParser(object):
    '''
        A record class for the NOAA Oil Library spreadsheet.
        - We manage a list of properties extracted from an Excel row for an
          oil.
        - The raw data from the Excel file will be a flat list, even for
          multidimensional properties like densities, viscosities, and
          distillation cuts.
    '''
    def __init__(self, property_names, values):
        '''
            :param property_names: A list of property names.

            :param values: A list of property values.

            Basically, we will do some light massaging of the names and values
            of our incoming properties, and then we will directly apply them
            to our __dict__.
            Additional customized properties will be defined for anything
            that requires special treatment.
        '''
        file_columns = [slugify_filename(c).lower()
                        for c in property_names]
        values = [v.strip() if v is not None else None
                  for v in values]
        row_dict = dict(izip_longest(file_columns, values))

        self._privatize_data_properties(row_dict)

        self.__dict__.update(row_dict)

    def _privatize_data_properties(self, kwargs):
        '''
            Certain named data properties need to be handled as special cases
            by the parser.  So in order to do this, we need to turn them into
            private members.
            This will allow us to create special case properties that have the
            original property name.
        '''
        for name in ('synonyms',
                     'pour_point_min_k', 'pour_point_max_k',
                     'flash_point_min_k', 'flash_point_max_k',
                     'preferred_oils', 'product_type',
                     'cut_units', 'oil_class'):
            self._privatize_data_property(kwargs, name)
        pass

    def _privatize_data_property(self, kwargs, name):
        '''
            Prepend a named keyward argument with an underscore,
            making it a 'private' property.
        '''
        new_name = '_{}'.format(name)

        kwargs[new_name] = kwargs[name]
        del kwargs[name]

    def get_interface_properties(self):
        '''
            These are all the property names that define the data in an
            Oil Library record.  They include the raw data column names
            plus any date items that needed to be redefined as special cases.
        '''
        props = set([k for k in self.__dict__
                     if not k.startswith('_')])
        props = props.union(set([p for p in dir(self.__class__)
                                 if isinstance(getattr(self.__class__, p),
                                               property)]))
        return props

    @property
    def oil_id(self):
        return self.adios_oil_id

    @property
    def reference_date(self):
        '''
            There is no defined reference date in an Oil Library record.
            There is however the possibility that a year of publication is
            contained within the reference text.
            We will try to find a year value within the reference field
            and return it.  Otherwise we return None
        '''
        if self.reference is None:
            return None
        else:
            expression = re.compile(r'\d{4}')
            occurences = expression.findall(self.reference)

            if len(occurences) == 0:
                return None
            else:
                # just return the first one
                return occurences[0]

    @property
    def pour_point_min_k(self):
        min_k, max_k = self._pour_point_min_k, self._pour_point_max_k

        if min_k == '<':
            min_k = None
        elif min_k == '>':
            min_k = max_k

        return min_k

    @property
    def pour_point_max_k(self):
        min_k, max_k = self._pour_point_min_k, self._pour_point_max_k

        if min_k == '>':
            max_k = None

        return max_k

    @property
    def flash_point_min_k(self):
        min_k, max_k = self._flash_point_min_k, self._flash_point_max_k

        if min_k == '<':
            min_k = None
        elif min_k == '>':
            min_k = max_k

        return min_k

    @property
    def flash_point_max_k(self):
        min_k, max_k = self._flash_point_min_k, self._flash_point_max_k

        if min_k == '>':
            max_k = None

        return max_k

    @property
    def preferred_oils(self):
        return True if self._preferred_oils == 'X' else False

    @property
    def product_type(self):
        if self._product_type is not None:
            return self._product_type.lower()
        else:
            return None

    @property
    def cut_units(self):
        if self._cut_units is not None:
            return self._cut_units.lower()
        else:
            return None

    @property
    def oil_class(self):
        if self._oil_class is not None:
            return self._oil_class.lower()
        else:
            return None

    @property
    def synonyms(self):
        '''
            Synonyms is a single string field that contains a comma separated
            list of substring names
        '''
        if self._synonyms is None or self._synonyms.strip() == '':
            return None
        else:
            return [{'name': s.strip()}
                    for s in self._synonyms.split(',')
                    if len(s) > 0]

    def get_property_sets(self, num_sets, obj_name, obj_argnames,
                          required_obj_args):
        '''
            Generalized method of getting lists of data sets out of our record.

            Since our data source is a single fixed row of data, there will be
            a number of fixed subsets of object data attributes, but they may
            or may not be filled with data.
            For these property sets, the column names are organized with the
            following naming convention:
                '<attr><instance>_<sub_attr>'

            Where:
                <attr>     = The name of the attribute list.
                <instance> = An index in the range [1...N+1] where N is the
                             number of instances in the list.
                <sub_attr> = The name of an attribute contained within an
                             instance of the list.

            Basically we will return a set of object properties for each
            instance that contains a defined set of required argument
            attributes.
        '''
        ret = []

        for i in range(1, num_sets + 1):
            obj_kwargs = {}

            parser_attrs = ['{}{}_{}'.format(obj_name, i, a)
                            for a in obj_argnames]

            for attr, obj_arg in zip(parser_attrs, obj_argnames):
                if hasattr(self, attr):
                    value = getattr(self, attr)

                    if value is not None and value != '':
                        obj_kwargs[obj_arg] = value

            if all([i in obj_kwargs for i in required_obj_args]):
                ret.append(obj_kwargs)

        return ret

    @property
    def densities(self):
        return self.get_property_sets(4, 'density',
                                      ('kg_m_3', 'ref_temp_k', 'weathering'),
                                      ('kg_m_3', 'ref_temp_k'))

    @property
    def kvis(self):
        return self.get_property_sets(6, 'kvis',
                                      ('m_2_s', 'ref_temp_k', 'weathering'),
                                      ('m_2_s', 'ref_temp_k'))

    @property
    def dvis(self):
        return self.get_property_sets(6, 'dvis',
                                      ('kg_ms', 'ref_temp_k', 'weathering'),
                                      ('kg_ms', 'ref_temp_k'))

    @property
    def cuts(self):
        return self.get_property_sets(15, 'cut',
                                      ('vapor_temp_k', 'liquid_temp_k',
                                       'fraction'),
                                      ('vapor_temp_k', 'fraction'))

    @property
    def toxicities(self):
        effective = self.get_property_sets(3, 'tox_ec',
                                           ('species', '24h', '48h', '96h'),
                                           ('species',))

        lethal = self.get_property_sets(3, 'tox_lc',
                                        ('species', '24h', '48h', '96h'),
                                        ('species',))

        [(e.update({'tox_type': 'EC'})) for e in effective]
        [(l.update({'tox_type': 'LC'})) for l in lethal]

        all_tox = effective + lethal

        for t in all_tox:
            for d in ('24h', '48h', '96h'):
                if d in t:
                    t['after_{}'.format(d)] = t[d]

        return all_tox
