<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>searchex – Dokumentation</title>
</head>
<body>
<h1>searchex – Dokumentation</h1>

<p><strong>Version:</strong> 0.2.0<br>
<strong>Plattform:</strong> Windows 10/11 (64‑bit)<br>
<strong>Technik:</strong> PySide6 (Qt) UI, C++ Extension via pybind11, scikit‑build‑core, CMake</p>

<hr>

<h2>Inhalt</h2>
<ol>
  <li><a href="#ueberblick">1. Überblick</a></li>
  <li><a href="#voraussetzungen">2. Voraussetzungen</a></li>
  <li><a href="#verzeichnisstruktur">3. Verzeichnisstruktur</a></li>
  <li><a href="#build-wheel">4. Build &amp; Installation (Wheel)</a></li>
  <li><a href="#starten">5. Starten</a></li>
  <li><a href="#bedienung">6. Bedienung</a></li>
  <li><a href="#optionen">7. Suchoptionen</a></li>
  <li><a href="#leistung">8. Leistung &amp; Responsivität</a></li>
  <li><a href="#logging">9. Logging &amp; Fehlermeldungen</a></li>
  <li><a href="#binary">10. Binärdateien &amp; Vorschau</a></li>
  <li><a href="#exe">11. Packen zu .exe (PyInstaller)</a></li>
  <li><a href="#troubleshooting">12. Troubleshooting</a></li>
  <li><a href="#faq">13. FAQ</a></li>
  <li><a href="#lizenz">14. Lizenz</a></li>
</ol>

<hr>

<h2 id="ueberblick">1. Überblick</h2>
<p><em>searchex</em> ist ein schneller, multithreaded Datei‑Scanner mit moderner Qt‑Oberfläche (PySide6). 
Rechenintensive Arbeit (Datei lesen, Muster finden) passiert in einem C++‑Modul (<code>searchex_native</code>) via pybind11.
Das Programm durchsucht rekursiv Dateien und kann sowohl Text‑ als auch Binärdateien prüfen. Funde werden pro Datei als Kacheln
angezeigt – inklusive Zeilennummern, Dateigröße, Vorschau und Direkt‑Sprung zur ersten Fundstelle.</p>

<hr>

<h2 id="voraussetzungen">2. Voraussetzungen</h2>
<ul>
  <li>Windows 10/11, 64‑bit</li>
  <li>Python 3.13 (64‑bit)</li>
  <li>Visual Studio 2022 Community mit &bdquo;Desktopentwicklung mit C++&ldquo;</li>
  <li>Build‑Tools: CMake &ge; 3.27, Ninja, pybind11[global], scikit‑build‑core</li>
</ul>

<pre><code>python -m pip install -U pip build scikit-build-core pybind11[global] cmake ninja
</code></pre>

<hr>

<h2 id="verzeichnisstruktur">3. Verzeichnisstruktur</h2>
<pre><code>searchex/
├─ pyproject.toml
├─ CMakeLists.txt
├─ README.md
├─ app.py
├─ resources/
│  ├─ logo.png
│  └─ logo.ico (optional für EXE)
├─ src/
│  ├─ cpp/
│  │  └─ cpp.cpp                (C++ Quelle für pybind11)
│  └─ searchex/
│     └─ __init__.py            (lädt searchex_native)
└─ logs/                        (wird zur Laufzeit angelegt)
</code></pre>

<hr>

<h2 id="build-wheel">4. Build &amp; Installation (Wheel)</h2>
<p>Das native Modul wird mit scikit‑build‑core und CMake gebaut.</p>
<pre><code># 1) Wheel bauen
python -m build --wheel .

# 2) Wheel installieren (überschreiben, keine Deps)
pip install --force-reinstall --no-deps dist\searchex-0.2.0-*.whl
</code></pre>

<p><strong>Wichtig:</strong> <code>CMakeLists.txt</code> muss im Projekt‑Root liegen und eine <code>install(TARGETS ...)</code>‑Regel besitzen,
damit die erzeugte <code>.pyd</code> im Wheel landet.</p>

<hr>

<h2 id="starten">5. Starten</h2>
<pre><code>python app.py
</code></pre>
<p>Optional kannst du das Fenster‑Icon setzen (bereits vorbereitet):</p>
<pre><code>app.setWindowIcon(QIcon("resources/logo.png"))
</code></pre>

<hr>

<h2 id="bedienung">6. Bedienung</h2>
<ol>
  <li><strong>Pfad wählen</strong>: Ordner oder Datei per Dialog wählen oder per Drag &amp; Drop in das Pfadfeld ziehen.</li>
  <li><strong>Suchmuster</strong>: Im Feld &bdquo;Search patterns&ldquo; pro Zeile ein Muster eintragen (Plaintext oder Regex).</li>
  <li><strong>Optionen</strong>: Case‑sensitive, Regex, Whole word, Name‑Matching, Hidden Files, Max. Dateigröße, Threads.</li>
  <li><strong>Start</strong>: &bdquo;Start&ldquo; klicken. Fortschritt und Anzahl verarbeiteter Dateien siehst du in der Statusleiste.</li>
  <li><strong>Ergebnisse</strong>: Kacheln zeigen Dateiname, Pfad, Größe, &bdquo;Text/Binary&ldquo;, Trefferzahl und <em>Zeilennummern</em>.</li>
  <li><strong>Aktionen pro Kachel</strong>: <em>Open</em>, <em>Reveal in Explorer</em>, <em>Jump to first hit</em>.</li>
  <li><strong>Fehler</strong>: &bdquo;Errors / skipped files&ldquo; ist einklappbar und listet Probleme (z. B. Zugriffsfehler).</li>
</ol>

<hr>

<h2 id="optionen">7. Suchoptionen</h2>
<ul>
  <li><strong>Case sensitive</strong>: ASCII‑Groß/Klein beachten.</li>
  <li><strong>Regex</strong>: Muster als ECMAScript‑Regex interpretieren.</li>
  <li><strong>Whole word</strong>: Treffer nur an Wortgrenzen (Substring‑Modus).</li>
  <li><strong>Match file/folder names</strong>: Muster gegen Dateinamen/Ordnernamen prüfen (schnell, ohne Dateiinhalt zu öffnen).</li>
  <li><strong>Include hidden</strong>: Versteckte Dateien/Ordner einschließen.</li>
  <li><strong>Max MB</strong>: 0 = unbegrenzt; sonst werden größere Dateien übersprungen.</li>
  <li><strong>Threads</strong>: Maximale Parallelität (Task‑Threads für Dateien).</li>
</ul>

<hr>

<h2 id="leistung">8. Leistung &amp; Responsivität</h2>
<ul>
  <li>Das C++‑Modul gibt während Datei‑I/O und Matching den Python‑GIL frei, damit die Qt‑Events weiterlaufen.</li>
  <li>Ergebnis‑Rendering erfolgt in kleinen Batches über einen Timer; das UI bleibt flüssig.</li>
  <li>Für sehr große Dateien empfiehlt sich ein Limit über &bdquo;Max MB&ldquo;.</li>
</ul>

<hr>

<h2 id="logging">9. Logging &amp; Fehlermeldungen</h2>
<p>Logs werden in <code>logs/app.log</code> geschrieben (Rolling‑File, UTF‑8). 
Bei Problemen erscheinen Einträge auch in der Liste &bdquo;Errors / skipped files&ldquo;.</p>

<hr>

<h2 id="binary">10. Binärdateien &amp; Vorschau</h2>
<ul>
  <li>Binärdateien werden anhand einer Heuristik erkannt (z. B. Nullbytes, Steuerzeichenanteil).</li>
  <li>Textvorschau zeigt Kontext um den ersten Treffer; bei Binärdateien erscheint ein Hex‑Snippet.</li>
</ul>

<hr>

<h2 id="exe">11. Packen zu .exe (PyInstaller)</h2>
<ol>
  <li>Icon konvertieren: <code>resources\logo.ico</code> (PNG bleibt für das Fenster‑Icon).</li>
  <li>Wheel lokal installieren, damit <code>searchex_native</code> verfügbar ist.</li>
</ol>
<pre><code>python -m build --wheel .
pip install --force-reinstall --no-deps dist\searchex-*.whl

pyinstaller app.py ^
  --name searchex ^
  --onedir ^
  --noconsole ^
  --icon resources\logo.ico ^
  --add-data "resources\logo.png;resources" ^
  --collect-all PySide6 ^
  --collect-binaries searchex
</code></pre>
<p>Ergebnis: <code>dist\searchex\searchex.exe</code> (ganzen Ordner verteilen). 
Für One‑file ersetze <code>--onedir</code> durch <code>--onefile</code>.</p>

<hr>

<h2 id="troubleshooting">12. Troubleshooting</h2>
<ul>
  <li><strong>Mini‑Wheel (~1&nbsp;KB)</strong>: In <code>CMakeLists.txt</code> fehlt die <code>install(TARGETS ...)</code>‑Regel.</li>
  <li><strong>Backend‑Pfad falsch</strong>: <code>build-backend = "scikit_build_core.build"</code> (mit Unterstrichen).</li>
  <li><strong>README fehlt</strong>: <code>readme = "README.md"</code> erfordert eine Datei im Root.</li>
  <li><strong>CMakeLists nicht im Root</strong>: scikit‑build‑core erwartet sie im Projekt‑Root.</li>
  <li><strong>Interpreter‑Mismatch</strong>: Wheel immer mit genau dem Python bauen/verwenden (z. B. <code>cp313 win_amd64</code>).</li>
  <li><strong>pybind11 nicht gefunden</strong>: <code>pip install pybind11[global]</code>.</li>
  <li><strong>Qt‑Plugins fehlen in EXE</strong>: PyInstaller mit <code>--collect-all PySide6</code> bauen.</li>
  <li><strong>Button‑Callback gibt bool statt Pfad</strong>: beim <code>clicked.connect</code> ein Dummy‑Argument verwenden, z. B.:<br>
  <code>lambda checked=False, p=path, pos=first_pos, b=is_bin: self.open_preview(p, pos, b)</code></li>
</ul>

<hr>

<h2 id="faq">13. FAQ</h2>
<p><strong>Warum ist ein Treffer in Binärdateien manchmal schwer zu interpretieren?</strong><br>
Weil die Daten nicht textuell sind; nutze die Hex‑Vorschau oder grenze mit Dateifiltern ein.</p>

<p><strong>Kann ich nur bestimmte Dateitypen durchsuchen?</strong><br>
Ja – Erweiterungsidee: einfache Pattern‑Filter (z. B. <code>*.cpp;*.h</code>) lassen sich leicht ergänzen.</p>

<p><strong>Speichert searchex Einstellungen?</strong><br>
Aktuell nicht dauerhaft; QSettings ließe sich einfach hinzufügen.</p>

<hr>

<h2 id="lizenz">14. Lizenz</h2>
<p>MIT‑Lizenz (Projektinhaber eintragen).</p>

</body>
</html>
