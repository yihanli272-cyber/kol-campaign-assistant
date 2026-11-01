"""Generate a minimal synthetic XLSX in a TemporaryDirectory, never from real data."""
import json
from pathlib import Path
from xml.sax.saxutils import escape
import zipfile
from creator_registry import FIELD_MAP

FIXTURE=Path(__file__).with_name('fixtures')/'registry_source.json'


def fixture_rows():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def write_fixture_workbook(path):
    path=Path(path)
    headers=list(FIELD_MAP)
    def column(index):
        value=''
        while index:
            index,rem=divmod(index-1,26);value=chr(65+rem)+value
        return value
    def cell(ref,value,numeric=False):
        return f'<c r="{ref}"><v>{escape(str(value))}</v></c>' if numeric else f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
    rows=['<row r="1">'+''.join(cell(column(i+1)+'1',h) for i,h in enumerate(headers))+'</row>']
    for index,item in enumerate(fixture_rows(),2):
        record={field:'' for field in FIELD_MAP.values()}
        record.update(reported_description='SYNTHETIC TEST ONLY',reported_position='Synthetic test creator',
                      creator_region='Test region',reported_language='Test language',
                      source_verification_status='synthetic_test_only',data_source='synthetic_fixture',
                      export_date='2026-01-01',source_file='synthetic_fixture.xlsx')
        record.update({k:v for k,v in item.items() if k in record})
        rows.append(f'<row r="{index}">'+''.join(cell(column(i+1)+str(index),record[FIELD_MAP[h]],
                    h=='账号ID' and item['_id_cell_type']=='n') for i,h in enumerate(headers))+'</row>')
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="统一达人库" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml',f'<worksheet xmlns="{ns}"><sheetData>'+''.join(rows)+'</sheetData></worksheet>')
    return path
