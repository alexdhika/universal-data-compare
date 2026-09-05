import base64
import io
import pandas as pd
from odoo import models, fields, api
from odoo.exceptions import UserError
import xlrd
import xlsxwriter

class UniversalDataCompare(models.Model):
    _name = 'data_compare'
    _description = 'Universal Data Compare'
    _order = 'write_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    excel_file = fields.Binary("File Excel", required=True, tracking=True)
    excel_file_name = fields.Char(tracking=True)

    config_id = fields.Many2one('data_compare_config', string='Model Config', required=True, tracking=True)
    config_model = fields.Many2one('ir.model', string='Model', related='config_id.model')
    unpivot = fields.Boolean(string='Unpivot', related='config_id.unpivot')

    line_ids = fields.One2many(
        'data_compare_line',
        'compare_id',
        string="Result",
        tracking=True
    )

    line_count = fields.Integer(
        string="Total Result",
        compute="_compute_line_count",
        tracking=True
    )

    unchecked_columns = fields.Text(
        string="Kolom Excel yang Tidak Dicek",
        readonly=True,
        tracking=True
    )

    @api.depends('line_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    def action_check(self):

        if not self.excel_file:
            raise UserError("Upload file Excel terlebih dahulu.")

        self.line_ids.unlink()

        try:
            data = base64.b64decode(self.excel_file)
            file_name = (self.excel_file_name or '').lower()

            if file_name.endswith('.xlsx'):
                df = pd.read_excel(
                    io.BytesIO(data),
                    dtype=str,
                    engine='openpyxl'
                )

            elif file_name.endswith('.xls'):
                # cek apakah file sebenarnya HTML
                if data[:20].strip().startswith(b'<!DOCTYPE') or b'<html' in data[:200].lower():
                    # baca sebagai HTML table
                    tables = pd.read_html(io.BytesIO(data))
                    df = tables[0]
                    df.columns = df.iloc[0]
                    df = df[1:]
                    df = df.reset_index(drop=True)
                    df = df.fillna('')
                    df.columns = df.columns.astype(str).str.strip()
                else:
                    # benar-benar file xls binary
                    workbook = xlrd.open_workbook(file_contents=data)
                    sheet = workbook.sheet_by_index(0)

                    headers = sheet.row_values(0)

                    rows = []
                    for row_idx in range(1, sheet.nrows):
                        row_dict = {}
                        row_values = sheet.row_values(row_idx)

                        for col_idx, header in enumerate(headers):
                            row_dict[header] = str(row_values[col_idx]).strip()

                        rows.append(row_dict)

                    df = pd.DataFrame(rows)
            else:
                raise UserError("Format file harus .xls atau .xlsx")

            df = df.fillna('')

        except Exception as e:
            raise UserError(f"Gagal membaca file Excel: {e}")


        df = df.loc[:, df.columns.notna()]

        config_field_mappings = [
            (line.excel_column, line.field_id.name, line.unpivot_value)
            for line in self.config_id.field_mapping_ids
        ]
        # raise UserError(config_field_mappings)

        # ambil kolom dari mapping
        mapping_excel_columns = [x[0] for x in config_field_mappings]

        # kolom yang ada di file
        file_columns = [str(col).strip() for col in df.columns]

        # ================= VALIDASI PRIMARY & INFORMATIONAL COLUMN =================
        primary_col = (self.config_id.primary_excel_column or '').strip()
        informational_col = (self.config_id.informational_excel_column or '').strip()

        missing_required_columns = []

        if primary_col and primary_col not in file_columns:
            missing_required_columns.append(f"Primary Excel Column '{primary_col}'")

        if informational_col and informational_col not in file_columns:
            missing_required_columns.append(f"Informational Excel Column '{informational_col}'")

        if missing_required_columns:
            raise UserError(
                "Kolom berikut tidak ditemukan di file Excel:\n- "
                + "\n- ".join(missing_required_columns)
            )

        # ============================================================================

        # kolom yang tidak dicek
        unchecked = [
            col for col in file_columns
            if col not in mapping_excel_columns
        ]

        self.unchecked_columns = "\n".join(unchecked) if unchecked else "Semua kolom dicek"

        total_match = 0
        total_mismatch = 0
        total_not_found = 0

        all_record = self.env[self.config_id.model.model].sudo().search(eval(self.config_id.filter_domain))

        primary_field = self.config_id.primary_key.name
        # cek duplikat primary key jika bukan unpivot
        if not self.config_id.unpivot:
            duplicate_keys = []
            seen_keys = set()

            for r in all_record:
                key = r[primary_field]
                if key in seen_keys:
                    duplicate_keys.append(str(key))
                else:
                    seen_keys.add(key)

            if duplicate_keys:
                raise UserError(
                    "Ditemukan data duplikat pada primary key berikut:\n- "
                    + "\n- ".join(sorted(set(duplicate_keys)))
                    + "\n\nTambahkan filter domain di konfigurasi tabel untuk menghindari data ganda."
                )

        # baru buat record_map kalau aman
        if not self.config_id.unpivot:
            record_map = {r[self.config_id.primary_key.name]: r for r in all_record}
        else:
            # jika unpivot maka promary key adalah gabungan primary key dan unpivot field
            record_map = {r[self.config_id.primary_key.name] + '-' + r[self.config_id.unpivot_field.name]: r for r in all_record}

        not_found_cache = set()

        # LOOP EXCEL ke ODOO
        for index, row in df.iterrows():
            for col in df.columns:
                value = row[col]

                self.check_value(row[self.config_id.primary_excel_column],
                    row[self.config_id.informational_excel_column],
                    col,value,record_map,not_found_cache,
                    config_field_mappings)

    def check_value(self,primary_excel_value,informational_excel_value,excel_kolom_name,
                    excel_value,record_map,not_found_cache,config_field_mappings):

        odoo_field = False
        odoo_value = ''

        # cari odoo field di field mapping
        for excel_col, odoo_col, unpivot_value in config_field_mappings:
            if excel_col == excel_kolom_name:
                odoo_field = odoo_col
                unpivot_value = unpivot_value
                break

        if odoo_field:
            # cari record berdasarkan primary key
            if not self.config_id.unpivot:
                r = record_map.get(primary_excel_value)
            else:
                r = record_map.get(primary_excel_value + '-' + unpivot_value)
                # jika ada duplikat pada unpivot record, tampikan primari=y key + unpivot value
                if r and len(r) > 1:
                    raise UserError(
                        "Ditemukan data duplikat pada primary key dan unpivot field berikut:\n- "
                        + "\n- " + primary_excel_value + ' - ' + unpivot_value
                        + "\n\nTambahkan filter domain di konfigurasi tabel untuk menghindari data ganda."
                        )

            if not r:
                status = 'not_found'

                # Jika tidak ada yang duplikat, baru buat baris baru
                if not self.config_id.unpivot:
                    if primary_excel_value not in not_found_cache:
                        self._create_line(
                            primary_excel_value,
                            informational_excel_value,
                            '',
                            '',
                            '',
                            '',
                            status
                        )
                        not_found_cache.add(primary_excel_value)

            else:
                # ambil value odoo
                record = r
                field = record._fields.get(odoo_field)
                value = record[odoo_field]
                field_label = field.string

                # cast excel sesuai tipe field
                excel_val_casted = self._cast_excel_value(field, excel_value)

                # ambil odoo value sesuai tipe asli
                odoo_val_casted = record[odoo_field]

                # khusus many2one tetap compare display_name
                if field.type == 'many2one':
                    excel_val_casted = str(excel_value).strip()
                    odoo_val_casted = odoo_val_casted.display_name if odoo_val_casted else ''

                # khusus char tetap string compare
                elif field.type in ('char', 'text', 'selection'):
                    excel_val_casted = str(excel_value).strip()
                    odoo_val_casted = str(odoo_val_casted or '').strip()

                # float tolerance (opsional tapi sangat disarankan)
                elif field.type == 'float':
                    try:
                        excel_val_casted = float(excel_val_casted or 0)
                        odoo_val_casted = float(odoo_val_casted or 0)
                    except Exception:
                        pass

                # integer
                elif field.type == 'integer':
                    try:
                        excel_val_casted = int(excel_val_casted or 0)
                        odoo_val_casted = int(odoo_val_casted or 0)
                    except Exception:
                        pass

                # date
                elif field.type == 'date':
                    excel_val_casted = str(excel_val_casted or '')
                    odoo_val_casted = str(odoo_val_casted or '')

                # COMPARE
                # ================= NUMERIC COMPARISON =================
                if field.type in ('float', 'monetary'):
                    try:
                        excel_num = float(excel_val_casted) if excel_val_casted not in (False, None, '') else 0.0
                        odoo_num = float(odoo_val_casted) if odoo_val_casted not in (False, None, '') else 0.0

                        # default tolerance
                        tolerance = self.config_id.rounding_tolerance

                        # hanya kalau monetary DAN currency_field ada
                        if field.type == 'monetary' and field.currency_field:
                            currency = record[field.currency_field]
                            if currency and currency.rounding:
                                tolerance = currency.rounding

                        if abs(excel_num - odoo_num) <= tolerance:
                            status = 'match'
                        else:
                            status = 'mismatch'

                    except Exception:
                        status = 'mismatch'


                elif field.type == 'integer':
                    try:
                        excel_num = int(excel_val_casted or 0)
                        odoo_num = int(odoo_val_casted or 0)

                        if (excel_num - odoo_num) == 0:
                            status = 'match'
                        else:
                            status = 'mismatch'

                    except Exception:
                        status = 'mismatch'


                # ================= NON NUMERIC =================
                else:
                    excel_str = str(excel_val_casted or '').strip().lower()
                    odoo_str = str(odoo_val_casted or '').strip().lower()

                    # Jika tipe field adalah selection, cek match ke KEY atau ke LABEL-nya
                    if field.type == 'selection':
                        # Ambil daftar tuple selection (aman untuk list langsung maupun fungsi string)
                        if isinstance(field.selection, list):
                            selection_values = field.selection
                        elif isinstance(field.selection, str) and hasattr(self.env[self.config_id.model.model], field.selection):
                            selection_values = getattr(self.env[self.config_id.model.model], field.selection)()
                        else:
                            selection_values = []
                        
                        matched_selection = False
                        for key, label in selection_values:
                            # Cek apakah input excel cocok dengan database key ATAU display label (case-insensitive)
                            if excel_str == str(key).lower() or excel_str == str(label).lower():
                                matched_selection = True
                                break
                        
                        if matched_selection:
                            status = 'match'
                        else:
                            status = 'mismatch'

                    # Untuk field teks biasa / Many2one, cukup lowercase-kan saja agar aman dari beda huruf kapital
                    else:
                        if excel_str == odoo_str:
                            status = 'match'
                        else:
                            status = 'mismatch'

                # jika mismatch baru simpan
                if status == 'mismatch':
                    self._create_line(
                        primary_excel_value,
                        informational_excel_value,
                        unpivot_value,
                        field_label,
                        excel_val_casted,
                        odoo_val_casted,
                        status
                    )
                    
    def _create_line(self, primary_excel_value, informational_excel_value, 
                        unpivot_value=None, field_name=None,
                        excel_value=None, odoo_value=None, status=None):

        self.env['data_compare_line'].create({
            'compare_id': self.id,
            'primary_excel_value': primary_excel_value,
            'informational_excel_value': informational_excel_value,
            'unpivot_value': unpivot_value,
            'field_name': field_name,
            'excel_value': excel_value,
            'odoo_value': odoo_value,
            'status': status,
        })

    def action_clear_result(self):
        self.ensure_one()
        self.line_ids.unlink()

    def _normalize_date(self, value):
        if not value:
            return ''

        try:
            parsed = pd.to_datetime(value, dayfirst=True, errors='raise')
            return parsed.date()
        except Exception:
            return value

    def action_download_excel(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError("Tidak ada data hasil compare untuk didownload.")

        output = io.BytesIO()
        # Inisialisasi workbook menggunakan library xlsxwriter
        try:
            import xlsxwriter
        except ImportError:
            raise UserError("Library xlsxwriter tidak ditemukan di server.")
            
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Hasil Compare')

        # Format Styling
        header_format = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1, 'align': 'center'})
        mismatch_format = workbook.add_format({'font_color': 'red', 'border': 1})
        border_format = workbook.add_format({'border': 1})

        # Ambil label kolom dari config atau hardcode sesuai field line_ids
        headers = [
            'Primary Excel Value', 
            'Informational Excel Value', 
            'Unpivot Value',
            'Field Compared', 
            'Excel Value', 
            'Odoo Value', 
            'Status'
        ]

        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_format)

        # Isi data dari line_ids
        row = 1
        for line in self.line_ids:
            sheet.write(row, 0, line.primary_excel_value or '', border_format)
            sheet.write(row, 1, line.informational_excel_value or '', border_format)
            sheet.write(row, 2, line.unpivot_value or '', border_format)
            sheet.write(row, 3, line.field_name or '', border_format)
            sheet.write(row, 4, str(line.excel_value or ''), border_format)
            sheet.write(row, 5, str(line.odoo_value or ''), border_format)
            
            # Warnai merah jika status mismatch
            current_style = mismatch_format if line.status == 'mismatch' else border_format
            sheet.write(row, 6, line.status or '', current_style)
            row += 1

        # Atur lebar kolom
        sheet.set_column(0, 6, 20)
        
        workbook.close()
        output.seek(0)

        # Buat attachment
        file_base64 = base64.b64encode(output.read())
        output.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Hasil_Compare_%s.xlsx' % self.excel_file_name,
            'type': 'binary',
            'datas': file_base64,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        # Return action untuk trigger download otomatis
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'new',
        }

    def _cast_excel_value(self, field, excel_value):
        """
        Cast value dari Excel sesuai tipe field Odoo
        """
        if excel_value in (None, '', False):
            return False

        try:
            if field.type in ('float', 'monetary'):
                return float(str(excel_value).replace(',', '').strip())

            elif field.type == 'integer':
                return int(float(str(excel_value).replace(',', '').strip()))

            elif field.type == 'boolean':
                val = str(excel_value).strip().lower()
                if val in ('true', '1', 'yes', 'active'):
                    return True
                return False

            elif field.type == 'date':
                return self._normalize_date(excel_value)

            return str(excel_value).strip()

        except Exception:
            return excel_value