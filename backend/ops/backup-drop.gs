/**
 * Ardoise backup drop (decision 0012). Lives in the developer's Google account, at
 * script.google.com, deployed as a web app; setup in docs/backups.md.
 *
 * Every night the Ardoise server posts its encrypted backup here, and this files it in the
 * Drive folder below. It only accepts files: it never sends anything back, and the files are
 * encrypted before they leave the server, so the address and the secret can at worst let
 * someone add junk files.
 *
 * Clean-up goes by age alone, never by count or by "the first of the month", so junk can't push
 * real backups out or take their place: every copy is kept for a year (decision 0013). At about
 * 100 KB a night, that is under 40 MB.
 */

const FOLDER_NAME = "Ardoise sauvegardes";
const KEEP_DAYS = 365;
const NAME = /^ardoise-\d{8}-\d{6}\.tar\.gz\.age$/;

function doPost(e) {
  // The secret is a script property (Project settings › Script properties › SECRET), never code.
  const secret = PropertiesService.getScriptProperties().getProperty("SECRET");
  let body;
  try {
    body = JSON.parse(e.postData.contents);
  } catch (err) {
    return answer({ ok: false, error: "not json" });
  }
  if (!secret || body.secret !== secret) return answer({ ok: false, error: "forbidden" });
  if (!NAME.test(body.name || "")) return answer({ ok: false, error: "bad name" });

  const folder = backupFolder();
  const bytes = Utilities.base64Decode(body.data);
  folder.createFile(Utilities.newBlob(bytes, "application/octet-stream", body.name));
  prune(folder);
  return answer({ ok: true });
}

function backupFolder() {
  const found = DriveApp.getFoldersByName(FOLDER_NAME);
  return found.hasNext() ? found.next() : DriveApp.createFolder(FOLDER_NAME);
}

function prune(folder) {
  const now = new Date();
  const day = 24 * 60 * 60 * 1000;
  const files = [];
  const all = folder.getFiles();
  while (all.hasNext()) {
    const file = all.next();
    if (NAME.test(file.getName())) files.push(file);
  }
  for (const file of files) {
    // By when Drive received it, which a sender can't fake.
    const age = (now - file.getDateCreated()) / day;
    if (age > KEEP_DAYS) file.setTrashed(true);
  }
}

function answer(value) {
  return ContentService.createTextOutput(JSON.stringify(value)).setMimeType(
    ContentService.MimeType.JSON,
  );
}
