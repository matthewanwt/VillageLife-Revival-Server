"""Prepare a user's own original XAPK for a loopback-only server (Windows).

Source material is never uploaded or altered. An APK may only be installed
*after* a locally generated signature is verified. Keep the signing identity
across upgrades, otherwise Android will refuse in-place updates.

This is NOT a distribution/redistribution licence or a network-isolation tool.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import zipfile
from villagelife.core.limits import validate_apk_archive, MAX_ARCHIVE_ENTRIES

# Recoverable endpoint configuration from the verified historical client.
PATCHES={
 b'https://playvlg.playdemic.com/web/':b'http://10.0.2.2/web/',
 b'https://playvlg.playdemic.com/':b'http://10.0.2.2/',
 b'http://vlt-prod.cdn.playdemic.com/assets/v270/':b'http://10.0.2.2/assets/v270/',
 b'http://vlt-prod-backup.cdn.playdemic.com/assets/v270/':b'http://10.0.2.2/assets/v270/',
}
APK_PACKAGE='com.playdemic.villagelife.android'
APK_NAME=APK_PACKAGE+'.apk'
GOOGLE_GAMES_ENABLED=b'PARAM_AND_GAMEPLAYSERVICES_GOOGLE\x00\x00\x00YES\x00'
GOOGLE_GAMES_DISABLED=b'PARAM_AND_GAMEPLAYSERVICES_GOOGLE\x00\x00\x00NO\x00\x00'

def digest(path:Path)->str:
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def patch_library(data:bytes, transport_key: str | None = None)->bytes:
    original=data
    for old,new in PATCHES.items():
        if transport_key is not None:
            if len(transport_key) != 12 or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_' for c in transport_key):
                raise ValueError('Invalid native transport capability')
            new = new.replace(b'10.0.2.2/', b'10.0.2.2/' + transport_key.encode('ascii') + b'/')
        if len(new)>len(old):raise ValueError('Replacement exceeds original binary constant')
        count=data.count(old+b'\0')
        if count!=1:raise ValueError(f'Expected exactly one original endpoint; found {count}')
        pos=data.index(old+b'\0')
        data=data[:pos]+new+b'\0'*(len(old)-len(new))+data[pos+len(old):]
    # This client build enables the optional Google Play Games integration,
    # which attempts a Google sign-in even though the private local game server
    # authenticates locally. Disable that integration in the user's prepared
    # copy; achievements/leaderboards tied to Google Play Games will be absent.
    google_count=data.count(GOOGLE_GAMES_ENABLED)
    if google_count>1:
        raise ValueError('Google Play Games setting is ambiguous in the supplied client')
    google_games_disabled=google_count==1
    if google_games_disabled:
        data=data.replace(GOOGLE_GAMES_ENABLED,GOOGLE_GAMES_DISABLED)
    if data==original:raise ValueError('No original endpoint strings were changed')
    return data

def unpack_game(source:Path,out:Path)->tuple[Path,Path]:
    """Extract one APK and one OBB to a private directory, with archive bounds."""
    source=source.expanduser().resolve(strict=True)
    out=out.expanduser().resolve();out.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(source) as archive:
        if len(archive.infolist()) > MAX_ARCHIVE_ENTRIES:
            raise ValueError('XAPK contains too many entries')
        members={v.filename:v for v in archive.infolist() if not v.is_dir()}
        # APKPure XAPKs commonly put the expansion file below Android/obb/;
        # only the package-named base APK and its package-named main OBB are
        # acceptable.  Do not select an arbitrary split APK or unrelated OBB.
        apks=[v for v in members.values() if Path(v.filename).name == APK_NAME]
        obbs=[v for v in members.values()
              if Path(v.filename).name.startswith('main.')
              and Path(v.filename).name.endswith('.'+APK_PACKAGE+'.obb')]
        if len(apks)!=1 or len(obbs)!=1:
            raise ValueError('Expected one package APK and one matching main OBB in the supplied original XAPK')
        if apks[0].file_size>300*1024*1024 or obbs[0].file_size>3*1024**3:
            raise ValueError('Unexpected oversized APK or expansion file')
        raw=out/'original-client.apk';expansion=out/Path(obbs[0].filename).name
        for entry,target in ((apks[0],raw),(obbs[0],expansion)):
            temporary=target.with_suffix(target.suffix+'.incomplete')
            try:
                with archive.open(entry) as src, temporary.open('wb') as dst:
                    shutil.copyfileobj(src,dst,1024*1024)
                os.replace(temporary,target)
            finally:temporary.unlink(missing_ok=True)
    return raw,expansion

def make_unsigned(original_apk:Path,out:Path, transport_key: str | None = None)->Path:
    target=out/'client-local-unsigned.apk'
    with zipfile.ZipFile(original_apk) as source,zipfile.ZipFile(target,'w') as dest:
        validate_apk_archive(source)
        if 'lib/armeabi-v7a/libpdandroid.so' not in source.namelist():
            raise ValueError('Unsupported original APK: ARM32 game library absent')
        for entry in source.infolist():
            if entry.is_dir() or entry.filename.upper().startswith('META-INF/'):continue
            raw=source.read(entry)
            if entry.filename=='lib/armeabi-v7a/libpdandroid.so':raw=patch_library(raw, transport_key)
            dest.writestr(entry,raw)
    return target

def sign_local(unsigned:Path,out:Path,java_home:Path|None=None)->Path:
    """Java v1 signing matches the historical private setup; check Android compatibility before use.

    Signing secrets remain in the private app-data directory. No signing
    credentials are printed or written to the repository.
    """
    if java_home:
        base=java_home/'bin'
        keytool=str(base/'keytool.exe') if os.name=='nt' else str(base/'keytool')
        signer=str(base/'jarsigner.exe') if os.name=='nt' else str(base/'jarsigner')
    else:
        keytool=shutil.which('keytool');signer=shutil.which('jarsigner')
    if not keytool or not signer:
        raise FileNotFoundError('Java JDK keytool and jarsigner required for the private client')
    sign_dir=out/'signing';sign_dir.mkdir(parents=True,exist_ok=True)
    legacy_key=sign_dir/'village-local-signing.p12'
    legacy_password=sign_dir/'private-password.txt'
    identity = sign_dir if legacy_key.exists() or legacy_password.exists() else sign_dir/'identity'
    key=identity/'village-local-signing.p12'
    password_file=identity/'private-password.txt'
    if key.exists()!=password_file.exists():
        raise ValueError('Existing signing identity is incomplete; restore its backup before proceeding')
    if not key.exists():
        password=secrets.token_urlsafe(32)
        env={**os.environ,'VL_SIGNING_PASSWORD':password}
        with tempfile.TemporaryDirectory(prefix='.identity-',dir=sign_dir) as pending:
            pending=Path(pending)
            cmd=[keytool,'-genkeypair','-alias','preservation-local',
                 '-keystore',str(pending/key.name),'-storetype','PKCS12',
                 '-storepass:env','VL_SIGNING_PASSWORD',
                 '-keyalg','RSA','-keysize','2048','-validity','3650',
                 '-dname','CN=Village Life Private Local Test']
            subprocess.run(cmd,check=True,timeout=90,env=env,capture_output=True,text=True,
                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            (pending/password_file.name).write_text(password,encoding='utf-8')
            try:os.chmod(pending/password_file.name,0o600)
            except OSError:pass
            # Publish the pair together; cancelled first setup cannot leave one half.
            pending.rename(identity)
    else:
        password=password_file.read_text(encoding='utf-8')
    env={**os.environ,'VL_SIGNING_PASSWORD':password}
    signed=out/'client-local-signed.apk'
    subprocess.run([signer,'-keystore',str(key),'-storepass:env','VL_SIGNING_PASSWORD',
                    '-digestalg','SHA-256','-sigalg','SHA256withRSA',
                    '-signedjar',str(signed),str(unsigned),'preservation-local'],
                    check=True,timeout=180,env=env,capture_output=True,text=True,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    # -strict returns exit code 4 for the expected locally self-signed
    # preservation certificate on current JDKs.  Verification without strict
    # still fails for a broken/tampered archive, while accepting that this is
    # deliberately not a publicly trusted Android signing certificate.
    checked=subprocess.run([signer,'-verify',str(signed)],
                           check=False,timeout=60,env=env,capture_output=True,text=True,
                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if checked.returncode:
        detail=(checked.stderr or checked.stdout).strip().replace('\r',' ').replace('\n',' ')[:240]
        raise ValueError('Local APK signature verification failed'+(': '+detail if detail else ''))
    return signed

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--xapk',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True,
                        help='Private runtime directory outside Git/release output')
    parser.add_argument('--java-home',type=Path)
    parser.add_argument('--prepare-data',action='store_true',help='Derive local runtime tables and resource offsets')
    parser.add_argument('--skip-sign',action='store_true',
                        help='Diagnostics only: unsigned APK cannot be installed')
    args=parser.parse_args(argv)
    args.output.mkdir(parents=True,exist_ok=True)
    receipt=args.output/'prepared-client.json'
    receipt.unlink(missing_ok=True)
    original_hash=digest(args.xapk)
    raw,obb=unpack_game(args.xapk,args.output)
    capability_file = args.output / 'transport-key.txt'
    existing_key=capability_file.read_text(encoding='ascii',errors='replace').strip() if capability_file.exists() else ''
    if len(existing_key)!=12 or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_' for c in existing_key):
        pending_key=capability_file.with_suffix('.txt.pending')
        pending_key.write_text(secrets.token_urlsafe(9),encoding='ascii')
        os.replace(pending_key,capability_file)
        try: os.chmod(capability_file, 0o600)
        except OSError: pass
    transport_key = capability_file.read_text(encoding='ascii').strip()
    unsigned=make_unsigned(raw,args.output,transport_key)
    if args.prepare_data:
        from villagelife.protocol.original_client.source_assets import derive_runtime_assets
        derive_runtime_assets(obb,args.output)
    with zipfile.ZipFile(unsigned) as prepared_apk:
        google_games_disabled=GOOGLE_GAMES_DISABLED in prepared_apk.read('lib/armeabi-v7a/libpdandroid.so')
    signed=None if args.skip_sign else sign_local(unsigned,args.output,args.java_home)
    if digest(args.xapk)!=original_hash:raise ValueError('Original XAPK changed during preparation')
    if signed is not None:
        pending_receipt=receipt.with_suffix('.json.pending')
        pending_receipt.write_text(json.dumps({'version':1,'archive_sha256':original_hash,
            'apk_sha256':digest(signed),'transport_key_sha256':hashlib.sha256(transport_key.encode()).hexdigest()}),encoding='utf-8')
        os.replace(pending_receipt,receipt)
    print('Original archive untouched:',True)
    print('Original archive SHA-256:',original_hash)
    print('OBB prepared:',obb)
    print('Locally patched and signed APK:',signed or 'NOT SIGNED: diagnostics only')
    print('Optional Google Play Games connection disabled in prepared copy:',google_games_disabled)
    print('Client network isolation: NOT VERIFIED. Do not bypass the launcher checks.')
    return 0

if __name__=='__main__':raise SystemExit(main())
