from sqlalchemy.sql import text

from .utils import replace_id_and_version


__all__ = (
    'publish_legacy_page',
)


def publish_legacy_page(model, metadata, submission, registry):
    """Publish a Page (aka Module) as the legacy (zope-based) system
    would. This should trigger the same (in-database) logic used when
    the legacy system publishes a module.

    :param model: module
    :type model: :class:`litezip.Module`
    :type metadata: :class:`press.models.ModuleMetadata`
    :param submission: a two value tuple containing a userid
                       and submit message
    :type submission: tuple
    :param registry: the pyramid component architecture registry
    :type registry: :class:`pyramid.registry.Registry`

    """
    engine = registry.engines['common']
    t = registry.tables

    if model.id is None or metadata.id is None:  # pragma: no cover
        raise NotImplementedError()

    with engine.begin() as trans:
        result = trans.execute(
            t.latest_modules.select()
            .where(t.latest_modules.c.moduleid == metadata.id))
        # At this time, this code assumes an existing module
        existing_module = result.fetchone()
        major_version = existing_module.major_version + 1

        # Insert module metadata
        result = trans.execute(t.abstracts.insert()
                               .values(abstract=metadata.abstract))
        abstractid = result.inserted_primary_key[0]
        result = trans.execute(
            t.licenses.select()
            .where(t.licenses.c.url == metadata.license_url))
        licenseid = result.fetchone().licenseid
        result = trans.execute(t.modules.insert().values(
            moduleid=metadata.id,
            major_version=major_version,
            portal_type='Module',
            name=metadata.title,
            created=metadata.created,
            revised=metadata.revised,
            abstractid=abstractid,
            licenseid=licenseid,
            doctype='',
            submitter=submission[0],
            submitlog=submission[1],
            language=metadata.language,
            authors=metadata.authors,
            maintainers=metadata.maintainers,
            licensors=metadata.licensors,
            # TODO metadata does not currently capture parentage
            parent=None,
            parentauthors=None,
        ).returning(
            t.modules.c.module_ident,
            t.modules.c.moduleid,
            t.modules.c.version,
        ))
        ident, id, version = result.fetchone()

        # Insert subjects metadata
        stmt = (text('INSERT INTO moduletags '
                     'SELECT :module_ident AS module_ident, tagid '
                     'FROM tags WHERE tag = any(:subjects)')
                .bindparams(module_ident=ident,
                            subjects=list(metadata.subjects)))
        result = trans.execute(stmt)

        # Insert keywords metadata
        stmt = (text('INSERT INTO keywords (word) '
                     'SELECT iword AS word '
                     'FROM unnest(:keywords ::text[]) AS iword '
                     '     LEFT JOIN keywords AS kw ON (kw.word = iword) '
                     'WHERE kw.keywordid IS NULL')
                .bindparams(keywords=list(metadata.keywords)))
        trans.execute(stmt)
        stmt = (text('INSERT INTO modulekeywords '
                     'SELECT :module_ident AS module_ident, keywordid '
                     'FROM keywords WHERE word = any(:keywords)')
                .bindparams(module_ident=ident,
                            keywords=list(metadata.keywords)))
        trans.execute(stmt)

        # Rewrite the content with the id and version
        replace_id_and_version(model, id, version)

        # Insert module files (content and resources)
        with model.file.open('rb') as fb:
            result = trans.execute(t.files.insert().values(
                file=fb.read(),
                media_type='text/xml',
            ))
        fileid = result.inserted_primary_key[0]
        result = trans.execute(t.module_files.insert().values(
            module_ident=ident,
            fileid=fileid,
            filename='index.cnxml',
        ))

        # TODO Insert resource files (images, pdfs, etc.)

    return (id, version), ident
