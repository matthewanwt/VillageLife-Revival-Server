using System.IO.Compression;
using System.Security.Cryptography;
using System.Security.Cryptography.Pkcs;
using System.Security.Cryptography.X509Certificates;
using System.Text;

internal static class LocalApkSigner {
 static byte[] Utf(string value)=>Encoding.UTF8.GetBytes(value);
 static string Hash(byte[] data)=>Convert.ToBase64String(SHA256.HashData(data));
 static byte[] Bytes(ZipArchiveEntry entry){using var stream=entry.Open();using var memory=new MemoryStream();stream.CopyTo(memory);return memory.ToArray();}
 static byte[] Attributes(params (string Key,string Value)[] values){
  using var output=new MemoryStream();
  foreach(var (key,value) in values){var bytes=Utf(key+": "+value);int offset=0;bool first=true;while(offset<bytes.Length){if(!first)output.WriteByte(32);int count=Math.Min(first?70:69,bytes.Length-offset);output.Write(bytes,offset,count);output.Write(Utf("\r\n"));offset+=count;first=false;}}
  output.Write(Utf("\r\n"));return output.ToArray();
 }
 static void Add(ZipArchive zip,string name,byte[] bytes){var entry=zip.CreateEntry(name,CompressionLevel.Optimal);using var stream=entry.Open();stream.Write(bytes);}
 static void Sign(string input,string output,string keyFile,string passwordFile){
  string password=File.ReadAllText(passwordFile).Trim();using var rsa=RSA.Create(2048);X509Certificate2 cert;
  if(File.Exists(keyFile))cert=X509CertificateLoader.LoadPkcs12FromFile(keyFile,password,X509KeyStorageFlags.EphemeralKeySet|X509KeyStorageFlags.Exportable);
  else{var request=new CertificateRequest("CN=Village Life Local Preservation",rsa,HashAlgorithmName.SHA256,RSASignaturePadding.Pkcs1);cert=request.CreateSelfSigned(DateTimeOffset.UtcNow.AddDays(-1),DateTimeOffset.UtcNow.AddYears(10));File.WriteAllBytes(keyFile,cert.Export(X509ContentType.Pfx,password));}
  using(cert){
   File.Copy(input,output,false);
   using(var zip=ZipFile.Open(output,ZipArchiveMode.Update)){
    var sections=new List<(string Name,byte[] Bytes)>();
    using var manifest=new MemoryStream();manifest.Write(Attributes(("Manifest-Version","1.0"),("Created-By","Village Life Local Preservation")));
    foreach(var entry in zip.Entries.ToArray()){
     if(entry.FullName.StartsWith("META-INF/",StringComparison.OrdinalIgnoreCase)){entry.Delete();continue;}
     if(entry.FullName.EndsWith('/'))continue;
     var section=Attributes(("Name",entry.FullName),("SHA-256-Digest",Hash(Bytes(entry))));sections.Add((entry.FullName,section));manifest.Write(section);
    }
    var manifestBytes=manifest.ToArray();using var sf=new MemoryStream();sf.Write(Attributes(("Signature-Version","1.0"),("Created-By","Village Life Local Preservation"),("SHA-256-Digest-Manifest",Hash(manifestBytes))));
    foreach(var section in sections)sf.Write(Attributes(("Name",section.Name),("SHA-256-Digest",Hash(section.Bytes))));
    var sfBytes=sf.ToArray();var cms=new SignedCms(new ContentInfo(sfBytes),true);var signer=new CmsSigner(SubjectIdentifierType.IssuerAndSerialNumber,cert){DigestAlgorithm=new Oid("2.16.840.1.101.3.4.2.1"),IncludeOption=X509IncludeOption.EndCertOnly};cms.ComputeSignature(signer,true);
    Add(zip,"META-INF/MANIFEST.MF",manifestBytes);Add(zip,"META-INF/PRESERVE.SF",sfBytes);Add(zip,"META-INF/PRESERVE.RSA",cms.Encode());
   }
  }
  Verify(output);
 }
 static List<(byte[] Raw,Dictionary<string,string> Fields)> Sections(byte[] data){
  var text=Encoding.UTF8.GetString(data);var result=new List<(byte[],Dictionary<string,string>)>();
  foreach(var block in text.Split("\r\n\r\n",StringSplitOptions.RemoveEmptyEntries)){
   var lines=new List<string>();foreach(var line in block.Split("\r\n")){if(line.StartsWith(' ')&&lines.Count>0)lines[^1]+=line[1..];else lines.Add(line);}
   var fields=new Dictionary<string,string>();foreach(var line in lines){int colon=line.IndexOf(": ");if(colon>0)fields.Add(line[..colon],line[(colon+2)..]);}
   result.Add((Utf(block+"\r\n\r\n"),fields));
  }return result;
 }
 static void Verify(string file){
  using var zip=ZipFile.OpenRead(file);var mf=Bytes(zip.GetEntry("META-INF/MANIFEST.MF")!);var sf=Bytes(zip.GetEntry("META-INF/PRESERVE.SF")!);var signature=Bytes(zip.GetEntry("META-INF/PRESERVE.RSA")!);
  var cms=new SignedCms(new ContentInfo(sf),true);cms.Decode(signature);cms.CheckSignature(true);
  var manifests=Sections(mf);var signatures=Sections(sf);if(signatures[0].Fields["SHA-256-Digest-Manifest"]!=Hash(mf))throw new Exception("APK manifest signature digest mismatch");
  var byName=signatures.Skip(1).ToDictionary(s=>s.Fields["Name"]);int count=0;
  foreach(var section in manifests.Skip(1)){string name=section.Fields["Name"];if(Hash(Bytes(zip.GetEntry(name)!))!=section.Fields["SHA-256-Digest"]||Hash(section.Raw)!=byName[name].Fields["SHA-256-Digest"])throw new Exception("APK entry digest mismatch: "+name);count++;}
  if(count!=zip.Entries.Count(e=>!e.FullName.StartsWith("META-INF/",StringComparison.OrdinalIgnoreCase)&&!e.FullName.EndsWith('/')))throw new Exception("Unsigned APK entry detected");
 }
 public static int Run(string[] args){try{if(args.Length==5&&args[0]=="--sign-apk")Sign(args[1],args[2],args[3],args[4]);else if(args.Length==2&&args[0]=="--verify-apk")Verify(args[1]);else throw new Exception("Unknown local preparation command");Console.WriteLine("Local APK signature and entry digests verified.");return 0;}catch(Exception error){Console.Error.WriteLine("Local APK preparation failed: "+error.Message);return 1;}}
}
