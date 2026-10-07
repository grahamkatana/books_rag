# Book RAG for Android

One app for the two things a reader does with Book RAG: **ask** the library a question, and
**verify** a draft against it. It talks to the same API as the web apps
(`books.tekbridge.co.za` and `verify.books.tekbridge.co.za`). The admin app is not part of it.

## What it does

- **Voice**: tap the microphone to dictate a question, and turn on the speaker icon (or tap Read aloud on an answer) to hear answers. Uses the phone's own speech services; no audio is stored. See notes/ for details.
**Ask**
- Log in with the email and password an administrator gave you (there is no sign-up).
- **Your own server**: tap the "Server:" line on the login screen to enter the address of a
  different Book RAG server. Leave it empty to go back to the standard one. It must be an
  `https` address, and it can only be changed while logged out, so a login is never sent to a
  server other than the one that issued it.
- Ask a question; the answer streams in as it is written, with headings, lists and tables rendered.
- Choose what to search: Books, Papers or Both. With Books or Papers you can limit the search to
  particular titles.
- Citations the answer makes appear as numbered markers. Tap one under the answer to see the full
  reference, where it is in the source, and the book or paper behind it.
- Open the menu to switch between saved chats, start a new one, or delete one.

**Verify**
- Upload a Word document (`.docx`, up to 25 MB) or paste text (up to 20,000 characters).
- Watch each claim get its verdict. This takes minutes and carries on if you leave the screen.
- Tap a claim for the explanation and the evidence. From the menu: run it again, or ask a second
  model for its opinion.

Not built: the web verify app's view of the draft itself with its claims highlighted, and its
presentation mode. The phone shows the list of claims instead.

## Build and install

It builds the same way as the Finance RAG app, with the same tools (JDK 17, Android SDK 35).

```bash
cd android
./gradlew testDebugUnitTest      # the unit tests; no server, phone or emulator needed
./gradlew assembleDebug          # app/build/outputs/apk/debug/app-debug.apk
./gradlew assembleRelease        # app/build/outputs/apk/release/app-release.apk (signed, see below)
```

- **API address**: `https://books.tekbridge.co.za`, set in `app/build.gradle.kts`. To try a server
  on your own machine, put `api.baseUrl=http://10.0.2.2:5000` in `android/local.properties`
  (git-ignored). Delete that line before a release build, or it is built into it.
- **Signing**: a release build is signed when `android/keystore.properties` exists (git-ignored).
  It points at a key kept outside the repository. Without it the release APK is unsigned and
  Android will not install it.
- **Publishing**: log in to books.tekbridge.co.za as an administrator, open **Android app** in the
  sidebar and use **Publish a version**. Everyone else downloads it from that page.
- **Installing**: with USB debugging on, `adb install -r app/build/outputs/apk/release/app-release.apk`.
  Or copy the file to the phone and open it.

## How it is built

A vertical slice per feature: each one owns its API calls, its models, its view model and its
screen, and can be read top to bottom without opening another feature.

```
app/src/main/java/com/graham_katana/bookrag/
  BookRagApp.kt     the few long-lived objects, wired by hand (no DI library)
  MainActivity.kt   login or the two tabs, depending on whether someone is logged in
  core/
    auth/           Session (who is logged in) and its encrypted storage
    network/        ApiClient: address, login header, JSON, errors, server-sent events
    ui/             theme, markdown rendering
  feature/
    auth/           login
    chat/           asking, saved chats, citations
    library/        books and papers (used by chat for the source limit and for references)
    verify/         drafts, claims, verdicts
app/src/test/       JVM unit tests, one folder per slice
```

Rules the code follows:

- A screen only reads state and calls view-model functions. A view model only talks to its
  feature's API interface, so tests replace that interface with a fake.
- State is one immutable data class per screen, exposed as a `StateFlow`.
- `Session` is the only place that knows whether someone is logged in. The API client ends it
  when the server rejects the token, and every screen returns to login the same way.
- Features may use `core` and `library`. They do not use each other.

## Security notes

- No secrets in the repository. The signing key and its password live outside it.
- The login token is encrypted with an AES-256 key held in the Android Keystore, and Android
  backup is switched off.
- HTTPS only in release builds. Tokens are never logged.
- The API issues no refresh token, so when the login expires the app returns to the login screen.
- The app cannot do more than the logged-in account can; permissions are enforced by the API.
