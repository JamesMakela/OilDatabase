#!/usr/bin/env python
import logging
from collections import defaultdict

from openpyxl import load_workbook

from slugify import Slugify

from pprint import PrettyPrinter
pp = PrettyPrinter(indent=2, width=120)

custom_slugify = Slugify(to_lower=True)
custom_slugify.separator = '_'

logger = logging.getLogger(__name__)


class EnvCanadaOilExcelFile(object):
    ''' A specialized file reader for the Environment Canada oil spreadsheet.
        - This is an Excel spreadsheet with an .xlsx extension.  We can use
          the third party openpyxl package to reach the content.
        - The first column in the file contains the names of oil property
          categories.
        - The second column in the file contains the names of specific oil
          properties.
        - The rest of the columns in the file contain oil property values.
    '''
    def __init__(self, name):
        '''
            :param name: The name of the oil library import file
            :type name: A path as a string or unicode
        '''
        self.name = name

        self.wb = load_workbook(self.name, data_only=True)
        self.wb.get_sheet_names()

        self.db_sheet = self.wb.get_sheet_by_name('Database')

        self.col_indexes = self._get_oil_column_indexes()
        self.field_indexes = self._get_row_field_names()

    def _get_oil_column_indexes(self):
        '''
            This is tailored to parse the data format of the Excel spreadsheet
            of oil properties by Environment Canada (2017).
            link: https://open.canada.ca/data/en/dataset?q=petroleum+products

            - A single oil can be represented by one or more contiguous
              columns.  They can sometimes be grouped by name, although this
              is not always true, especially with the refined products.
              It seems that the ESTS code is the only reliable way of grouping
              them.
            - The ESTS code is the way they identify the samples they test,
              and it contains two or three numbers separated by a period '.'.
              The first number seems to identify the species of the petroleum
              substance, and the rest identify a degree of weathering,
              either natural or simulated in a laboratory.
            - We will return a dict with oil names as keys and a list of
              associated column indexes as values.
        '''
        col_headers = defaultdict(list)

        for idx, col in enumerate(self.db_sheet.columns):
            if idx >= 2:
                # all columns should have a valid ESTS code
                ests_code = str(col[4].value).split('.')[0]
                col_headers[ests_code].append(idx)

        return col_headers

    def _get_row_field_names(self):
        '''
            This is tailored to parse the data format of the Excel spreadsheet
            of oil properties that was given to NOAA by Environment Canada
            (2017).

            Column 0 contains field category names in which each single
            category is represented by a contiguous group of rows, and only
            the first row contains the name of the category.

            Within the group of category rows, column 1 contains specific oil
            property names.  So to get a specific property for an oil, one
            needs to reference (category, property)
            A property name within a category is not unique.  For example,
            emulsion at 15C has multiple standard_deviation fields.

            There also exist rows that are not associated with any oil property
            which contain blank fields for both category and property.

            For field names, we would like to keep them lowercase, strip out
            the special characters, and separate the individual word components
            of the field name with '_'
        '''
        row_fields = defaultdict(lambda: defaultdict(list))
        row_prev_name = None

        for idx, row in enumerate(self.db_sheet.rows):
            if all([(r.value is None) for r in row[:2]]):
                category_name, field_name = None, None
            elif row[0].value is not None:
                category_name = custom_slugify(row[0].value)
                row_prev_name = category_name
                if row[1].value is not None:
                    field_name = custom_slugify(unicode(row[1].value))
                else:
                    field_name = None
            else:
                category_name = row_prev_name
                if row[1].value is not None:
                    field_name = custom_slugify(unicode(row[1].value))
                else:
                    field_name = None

            row_fields[category_name][field_name].append(idx)

        return row_fields

    def __repr__(self):
        return "<OilLibraryFile('%s')>" % (self.name)

    def get_record(self, name):
        '''
            Return the columns in the Excel sheet referenced by the name of an
            oil.
            Note: the Excel sheet columns object has no direct indexing,
                  only a next().  This is why we are using walk method to get
                  our indexed columns.
        '''
        return zip(*[[cell.value for cell in col]
                     for i, col in enumerate(self.db_sheet.columns)
                     if i in self.col_indexes[name]])

    def get_records(self):
        '''
            Iterate through all the oils, returning all the properties of each
            one.
        '''
        for name in self.col_indexes:
            yield self.field_indexes, self.get_record(name)
