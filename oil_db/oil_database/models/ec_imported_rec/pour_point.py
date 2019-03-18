#
# PyMODM model class for Environment Canada's pour point
# oil properties.
#
from pymodm.errors import ValidationError
from pymodm import EmbeddedMongoModel
from pymodm.fields import (CharField,
                           FloatField)


class PourPoint(EmbeddedMongoModel):
    min_temp_k = FloatField(blank=True)
    max_temp_k = FloatField(blank=True)
    weathering = FloatField(default=0.0)

    # may as well keep the extra stuff
    standard_deviation = FloatField(blank=True)
    replicates = FloatField(blank=True)
    method = CharField(max_length=32, blank=True)

    def __init__(self, **kwargs):
        if len(kwargs.keys()) > 0:
            # we will fail on any arguments that are not defined members
            # of this class
            for a, _v in kwargs.items():
                if (a not in self.__class__.__dict__):
                    del kwargs[a]

            if 'weathering' not in kwargs or kwargs['weathering'] is None:
                # Seriously?  What good is a default if it can't negotiate
                # None values?
                kwargs['weathering'] = 0.0

            if kwargs['min_temp_k'] is None and kwargs['max_temp_k'] is None:
                raise ValidationError('PourPoint obj needs at least one valid '
                                      'temperature, either min or max')

        super(PourPoint, self).__init__(**kwargs)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        min_temp = self.min_temp_k
        max_temp = self.max_temp_k
        w = self.weathering

        return ('<PourPoint([{}{} - {}{}], w={})>'
                .format(min_temp, '' if min_temp is None else 'K',
                        max_temp, '' if max_temp is None else 'K',
                        w))
