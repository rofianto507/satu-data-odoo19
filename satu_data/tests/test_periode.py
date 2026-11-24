from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import SatuDataCase


@tagged('post_install', '-at_install', 'satu_data')
class TestPeriode(SatuDataCase):

    def test_periode_tanggal_tidak_valid(self):
        Periode = self.env['satu_data.periode']
        with self.assertRaises(ValidationError):
            Periode.create({'name': 'Terbalik', 'tanggal_mulai': '2099-06-30',
                            'tanggal_akhir': '2099-01-01'})
        with self.assertRaises(ValidationError, msg='Bertumpuk dengan Uji 2095 Semester I'):
            Periode.create({'name': 'Tumpuk', 'tanggal_mulai': '2095-06-01',
                            'tanggal_akhir': '2095-09-30'})
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.env.cr.savepoint():
            Periode.create({'name': 'Uji 2095 Semester I', 'tanggal_mulai': '2099-01-01',
                            'tanggal_akhir': '2099-06-30'})

