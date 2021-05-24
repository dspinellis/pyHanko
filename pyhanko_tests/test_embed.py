import binascii
from datetime import datetime, timedelta
from io import BytesIO

import pytest
import tzlocal
from freezegun import freeze_time

from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils import writer, embed, generic, misc
from pyhanko_tests.samples import *


def _embed_test(w, fname, ufname, data, created=None, modified=None):

    ef_obj = embed.EmbeddedFileObject.from_file_data(
        w, data=data, mime_type='application/pdf',
        params=embed.EmbeddedFileParams(
            creation_date=created, modification_date=modified
        )
    )

    spec = embed.FileSpec(
        file_spec_string=fname, file_name=ufname,
        embedded_data=ef_obj, description='Embedding test'
    )
    embed.embed_file(w, spec)


@freeze_time('2020-11-01')
@pytest.mark.parametrize('incremental', [True, False])
def test_simple_embed(incremental):
    if incremental:
        w = IncrementalPdfFileWriter(BytesIO(MINIMAL))
    else:
        r = PdfFileReader(BytesIO(MINIMAL))
        w = writer.copy_into_new_writer(r)

    modified = datetime.now(tz=tzlocal.get_localzone())
    created = modified - timedelta(days=1)
    _embed_test(
        w, fname='vector-test.pdf', ufname='テスト.pdf',
        data=VECTOR_IMAGE_PDF,
        created=created, modified=modified
    )

    out = BytesIO()
    w.write(out)

    r = PdfFileReader(out)
    assert r.input_version == (1, 7)
    emb_lst = r.root['/Names']['/EmbeddedFiles']['/Names']
    assert len(emb_lst) == 2
    assert emb_lst[0] == 'vector-test.pdf'
    spec_obj = emb_lst[1]
    assert spec_obj['/Desc'] == 'Embedding test'
    assert spec_obj['/UF'] == 'テスト.pdf'
    stream = spec_obj['/EF']['/F']
    assert stream.data == VECTOR_IMAGE_PDF

    # FIXME This assertion will have to be corrected once I deal with the name
    #  parser's problems
    assert stream['/Subtype'] == '/application#2fpdf'

    assert stream['/Params']['/CheckSum'] \
           == binascii.unhexlify('caaf24354fd2e68c08826d65b309b404')
    assert generic.parse_pdf_date(stream['/Params']['/ModDate']) == modified
    assert generic.parse_pdf_date(stream['/Params']['/CreationDate']) == created

    assert '/AF' not in r.root


@freeze_time('2020-11-01')
@pytest.mark.parametrize('incremental', [True, False])
def test_embed_twice(incremental):
    r = PdfFileReader(BytesIO(MINIMAL))
    w = writer.copy_into_new_writer(r)

    modified = datetime.now(tz=tzlocal.get_localzone())
    created = modified - timedelta(days=1)
    _embed_test(
        w, fname='vector-test.pdf', ufname='テスト.pdf',
        data=VECTOR_IMAGE_PDF,
        created=created, modified=modified
    )

    if incremental:
        out = BytesIO()
        w.write(out)
        w = IncrementalPdfFileWriter(out)

    _embed_test(
        w, fname='some-other-file.pdf', ufname='テスト2.pdf',
        data=MINIMAL_AES256,
        created=created, modified=modified
    )

    out = BytesIO()
    w.write(out)

    r = PdfFileReader(out)
    emb_lst = r.root['/Names']['/EmbeddedFiles']['/Names']
    assert len(emb_lst) == 4
    assert emb_lst[0] == 'vector-test.pdf'
    spec_obj = emb_lst[1]
    assert spec_obj['/UF'] == 'テスト.pdf'
    stream = spec_obj['/EF']['/F']
    assert stream.data == VECTOR_IMAGE_PDF

    assert emb_lst[2] == 'some-other-file.pdf'
    spec_obj = emb_lst[3]
    assert spec_obj['/UF'] == 'テスト2.pdf'
    stream = spec_obj['/EF']['/F']
    assert stream.data == MINIMAL_AES256


@freeze_time('2020-11-01')
@pytest.mark.parametrize('incremental', [True, False])
def test_embed_with_af(incremental):
    if incremental:
        w = IncrementalPdfFileWriter(BytesIO(MINIMAL))
    else:
        r = PdfFileReader(BytesIO(MINIMAL))
        w = writer.copy_into_new_writer(r)

    modified = datetime.now(tz=tzlocal.get_localzone())
    created = modified - timedelta(days=1)
    ef_obj = embed.EmbeddedFileObject.from_file_data(
        w, data=VECTOR_IMAGE_PDF,
        params=embed.EmbeddedFileParams(
            creation_date=created, modification_date=modified
        )
    )

    spec = embed.FileSpec(
        file_spec_string='vector-test.pdf',
        embedded_data=ef_obj, description='Embedding test /w assoc file',
        af_relationship=generic.pdf_name('/Unspecified')
    )
    embed.embed_file(w, spec)
    out = BytesIO()
    w.write(out)
    r = PdfFileReader(out)
    assert r.input_version == (2, 0)
    emb_lst = r.root['/Names']['/EmbeddedFiles']['/Names']
    assert len(emb_lst) == 2
    assert emb_lst[0] == 'vector-test.pdf'
    spec_obj = emb_lst[1]
    assert '/UF' not in spec_obj
    assert spec_obj['/AFRelationship'] == '/Unspecified'
    stream = spec_obj['/EF']['/F']
    assert stream.data == VECTOR_IMAGE_PDF
    assert '/UF' not in spec_obj['/EF']

    assert r.root['/AF'].raw_get(0).reference == spec_obj.container_ref


def test_embed_without_ef_stream():
    r = PdfFileReader(BytesIO(MINIMAL))
    w = writer.copy_into_new_writer(r)

    spec = embed.FileSpec(
        file_spec_string='vector-test.pdf',
        description='Embedding test /w assoc file',
        af_relationship=generic.pdf_name('/Unspecified')
    )
    err_msg = "File spec does not have an embedded file stream"
    with pytest.raises(misc.PdfWriteError, match=err_msg):
        embed.embed_file(w, spec)