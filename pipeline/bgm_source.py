"""Verified music catalogs and single-track access to repository files."""
import contextlib
import hashlib
import io
import json
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
from urllib.error import HTTPError
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from .updates import _no_links

MAX_TRACK_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_CATALOG = 'https://raw.githubusercontent.com/lx-1203/NAU-CEA-News/main/assets/audio/music/MANIFEST.json'


def check_url(url, allow_local_http=False):
    if not isinstance(url, str) or re.search(r'[\x00-\x20\\]', url):
        raise ValueError('Invalid music source URL')
    value = urllib.parse.urlsplit(url)
    local = allow_local_http and value.scheme == 'http' and value.hostname == '127.0.0.1'
    if (not local and value.scheme != 'https') or not value.hostname or value.username or value.password or value.fragment:
        raise ValueError('Music sources require HTTPS without embedded credentials')
    return url


@contextlib.contextmanager
def _open(url, headers=None, allow_local_http=False):
    check_url(url, allow_local_http)
    request = urllib.request.Request(url, headers={'User-Agent':'NJAU-CEA-BGM/1.0', **(headers or {})})
    with urllib.request.urlopen(request, timeout=45) as response:
        check_url(response.url, allow_local_http)
        yield response


def _read(url, limit, allow_local_http=False):
    with _open(url, {'Cache-Control':'no-cache'}, allow_local_http) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Music metadata exceeds byte limit')
    return data


def validate_catalog(catalog):
    if not isinstance(catalog, dict) or not re.fullmatch(r'\d+\.\d+\.\d+', str(catalog.get('version',''))):
        raise ValueError('Invalid music catalog version')
    tracks = catalog.get('tracks')
    if not isinstance(tracks, list) or not tracks or len(tracks) > 10000:
        raise ValueError('Invalid music catalog tracks')
    ids, names, digests = set(), set(), {}
    for track in tracks:
        if not isinstance(track,dict):raise ValueError('Invalid track metadata')
        name, digest = track.get('path'), track.get('sha256')
        if (not isinstance(name,str) or len(name)>200 or name in {'.','..'}
            or re.search(r'[\x00-\x1f/\\:<>"?*|]',name) or name.endswith((' ','.'))
            or re.match(r'^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)',name,re.I)
            or Path(name).suffix.lower() not in {'.mp3','.ogg','.wav','.flac','.m4a'}):
            raise ValueError('Unsafe music filename')
        if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):
            raise ValueError('Invalid track SHA256')
        size=track.get('bytes')
        if type(size) is not int or not 0<size<=MAX_TRACK_BYTES:
            raise ValueError('Invalid track byte size')
        identity=track.get('id')
        if not isinstance(identity,str) or not identity or identity in ids or name.casefold() in names:
            raise ValueError('Duplicate or missing track identity')
        if not isinstance(track.get('title'),str) or not track['title'].strip():
            raise ValueError('Missing track title')
        if digest in digests and digests[digest]!=size:raise ValueError('Conflicting track sizes for same SHA256')
        ids.add(identity);names.add(name.casefold());digests[digest]=size
    return catalog


def refresh_catalog(settings):
    """Read the live catalog and bind the audio source to a fixed revision."""
    url=settings.get('catalog_url',DEFAULT_CATALOG)
    channel=json.loads(_read(url,4*1024*1024))
    validate_catalog(channel)
    repository=settings.get('repository','lx-1203/NAU-CEA-News')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):
        raise ValueError('Invalid GitHub music repository')
    version=channel['version']
    if 'repository_files' in channel:
        source=channel['repository_files']
        ref=source.get('ref') if isinstance(source,dict) else None
        if not isinstance(ref,str) or not re.fullmatch('[0-9a-f]{40}',ref):
            raise ValueError('Repository music catalog requires a fixed Git commit')
        channel['download']=dict(track_base_url=f'https://raw.githubusercontent.com/{repository}/{ref}/assets/audio/music',
                                 catalog_url=url)
        channel['channel_version']=version
        return channel
    # Installations with an explicitly configured historical catalog retain its reader.
    base=f'https://github.com/{repository}/releases/download/music-pack-v{version}'
    try:
        frozen=json.loads(_read(base+'/MUSIC_MANIFEST.json',4*1024*1024))
    except HTTPError as error:
        if error.code!=404:raise
        # main can be pushed while a large release ZIP is still uploading as a
        # draft. Read GitHub's public release feed (no API rate limit/token).
        feed=ET.fromstring(_read(f'https://github.com/{repository}/releases.atom',2*1024*1024))
        published=[]
        prefix=f'https://github.com/{repository}/releases/tag/music-pack-v'
        for link in feed.iter('{http://www.w3.org/2005/Atom}link'):
            href=link.get('href','')
            if href.startswith(prefix) and re.fullmatch(r'\d+\.\d+\.\d+',href[len(prefix):]):
                published.append(href[len(prefix):])
        if not published:raise ValueError('No published music release is available') from error
        version=max(published,key=lambda item:tuple(map(int,item.split('.'))))
        base=f'https://github.com/{repository}/releases/download/music-pack-v{version}'
        frozen=json.loads(_read(base+'/MUSIC_MANIFEST.json',4*1024*1024))
    validate_catalog(frozen)
    if frozen['version']!=version:raise ValueError('Published music version does not match its release')
    if version==channel['version'] and frozen!=channel:
        raise ValueError('Music channel and published release catalog disagree; retry after publication')
    archive=f'NJAU-CEA-Music-Pack-v{version}.zip'
    try:checksum=_read(base+f'/SHA256SUMS-v{version}.txt',32768).decode('utf-8-sig')
    except HTTPError as error:
        if error.code!=404 or version!='1.0.0':raise
        checksum=_read(base+'/SHA256SUMS.txt',32768).decode('utf-8-sig')
    matches=re.findall(r'^([0-9a-f]{64})\s+\*?'+re.escape(archive)+r'\s*$',checksum,re.M)
    if len(matches)!=1:raise ValueError('Missing or ambiguous published music archive checksum')
    frozen['download']=dict(archive_url=base+'/'+archive,archive_sha256=matches[0],catalog_url=base+'/MUSIC_MANIFEST.json')
    frozen['channel_version']=channel['version']
    return frozen


class RangeUnsupported(ValueError):
    pass


class RemoteZip(io.RawIOBase):
    """Seekable HTTP Range file; memory is bounded by each ZIP read request."""
    def __init__(self,url,maximum,allow_local_http=False):
        self.url=url;self.maximum=maximum;self.local=allow_local_http
        self.position=0;self.size=None;self.transferred=0
        self._range(0,0)

    def _range(self,start,end):
        with _open(self.url,{'Range':f'bytes={start}-{end}'},self.local) as response:
            if response.status!=206:raise RangeUnsupported('Server does not support byte-range music access')
            match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',response.headers.get('Content-Range',''))
            if not match:raise ValueError('Invalid Content-Range')
            a,b,size=map(int,match.groups())
            if (a,b)!=(start,end) or (self.size is not None and self.size!=size):raise ValueError('Inconsistent archive range')
            if not 0<size<=self.maximum:raise ValueError('Music archive exceeds byte budget')
            self.size=size
            data=response.read(end-start+2)
            if len(data)!=end-start+1:raise ValueError('Truncated or oversized music range')
            self.transferred+=len(data)
            return data

    def seekable(self):return True
    def readable(self):return True
    def tell(self):return self.position
    def seek(self,offset,whence=0):
        position=offset if whence==0 else self.position+offset if whence==1 else self.size+offset
        if whence not in (0,1,2) or position<0:raise ValueError('Invalid archive seek')
        self.position=position;return position
    def read(self,size=-1):
        size=self.size-self.position if size<0 else min(size,self.size-self.position)
        if size<=0:return b''
        if size>8*1024*1024:raise ValueError('ZIP structure requests too much memory')
        data=self._range(self.position,self.position+size-1)
        self.position+=len(data);return data


def _copy_track(incoming,track,partial):
    digest=hashlib.sha256();total=0
    with partial.open('xb') as output:
        while chunk:=incoming.read(min(1024*1024,track['bytes']-total+1)):
            total+=len(chunk)
            if total>track['bytes']:
                raise ValueError('Audio exceeds the catalog byte count')
            digest.update(chunk);output.write(chunk)
    if total!=track['bytes'] or digest.hexdigest()!=track['sha256']:
        raise ValueError('Audio SHA256 or size does not match the catalog')


def _extract(stream,track,partial):
    with zipfile.ZipFile(stream) as archive:
        suffix='/assets/audio/music/'+track['path']
        matches=[x for x in archive.infolist() if x.filename.endswith(suffix)]
        if len(matches)!=1:raise ValueError('Missing or ambiguous music archive member')
        member=matches[0]
        if (member.file_size!=track['bytes'] or member.flag_bits&1
                or member.compress_type not in {zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED}):
            raise ValueError('Invalid archived audio size or format')
        with archive.open(member) as incoming:
            _copy_track(incoming,track,partial)


def _repository_track(track,source,partial,local_music_directory,allow_local_http):
    base=check_url(source['track_base_url'],allow_local_http)
    if urllib.parse.urlsplit(base).query:
        raise ValueError('Repository music base URL cannot contain a query string')
    local=Path(local_music_directory)/track['path'] if local_music_directory is not None else None
    if local is not None:
        _no_links(local)
        if local.is_file():
            with local.open('rb') as incoming:
                _copy_track(incoming,track,partial)
            return dict(mode='local_repository_file',download_bytes=0)
    url=base.rstrip('/')+'/'+urllib.parse.quote(track['path'],safe='')
    with _open(url,allow_local_http=allow_local_http) as incoming:
        _copy_track(incoming,track,partial)
    return dict(mode='repository_file',download_bytes=track['bytes'])


def download_track(track,source,directory,*,local_music_directory=None,allow_local_http=False,
                   max_archive_bytes=MAX_ARCHIVE_BYTES):
    validate_catalog(dict(version='1.0.0',tracks=[track]))
    directory=Path(directory);_no_links(directory);directory.mkdir(parents=True,exist_ok=True)
    target=directory/(track['sha256']+Path(track['path']).suffix.lower())
    partial=directory/(target.name+'.part')
    _no_links(target);_no_links(partial)
    if target.exists() or partial.exists():raise FileExistsError('BGM download target already exists; clean managed cache first')
    if shutil.disk_usage(directory).free<track['bytes']+16*1024*1024:
        raise ValueError('Insufficient free disk for selected music track')
    try:
        if 'track_base_url' in source:
            receipt=_repository_track(track,source,partial,local_music_directory,allow_local_http)
            partial.rename(target)
            return target,receipt
        url=check_url(source['archive_url'],allow_local_http)
        if not re.fullmatch('[0-9a-f]{64}',source.get('archive_sha256','')):
            raise ValueError('Verified source archive checksum is required')
        try:
            with RemoteZip(url,max_archive_bytes,allow_local_http) as stream:
                _extract(stream,track,partial)
                receipt=dict(mode='range_zip',download_bytes=stream.transferred,archive_bytes=stream.size)
        except RangeUnsupported:
            # No permanent library download. The temporary ZIP is deleted even on exceptions.
            with _open(url,allow_local_http=allow_local_http) as response:
                length=response.headers.get('Content-Length')
                if length and int(length)>max_archive_bytes:raise ValueError('Music archive exceeds byte budget')
                budget=int(length) if length else max_archive_bytes
                if shutil.disk_usage(directory).free<budget+track['bytes']+16*1024*1024:
                    raise ValueError('Insufficient free disk for temporary music archive')
                with tempfile.TemporaryFile(dir=directory) as stream:
                    digest=hashlib.sha256();size=0
                    while chunk:=response.read(1024*1024):
                        size+=len(chunk)
                        if size>max_archive_bytes:raise ValueError('Music archive exceeds byte budget')
                        digest.update(chunk);stream.write(chunk)
                    if digest.hexdigest()!=source['archive_sha256']:raise ValueError('Music archive checksum mismatch')
                    stream.seek(0);_extract(stream,track,partial)
                    receipt=dict(mode='temporary_zip',download_bytes=size,archive_bytes=size)
        partial.rename(target)
        return target,receipt
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
