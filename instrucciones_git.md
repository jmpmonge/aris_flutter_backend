# Flutter web, Git y Netlify (Aris)

Raíz habitual de la app en este monorepo:

```bash
cd /Users/jose/proyectos/aris_flutter_backend/aris_flutter_v0.22
```

Si trabajas en el repo solo Flutter (`aris-flutter` en GitHub), usa esa carpeta como raíz en todos los comandos.

---

## 1. Crear la carpeta web (`build/web`)

**No hay que crear la carpeta a mano.** Flutter la genera al compilar.

### Requisito (una vez por máquina)

```bash
flutter config --enable-web
flutter doctor
```

En `flutter doctor`, la línea **Chrome** o **Web** debe aparecer disponible.

### Compilar (genera `build/web`)

```bash
flutter pub get
dart analyze
flutter build web --release
```

cd aris_flutter_v0.22
flutter pub get
dart analyze
flutter build web --release

Salida esperada:

| Ruta | Contenido |
|------|-----------|
| `build/web/index.html` | Entrada de la app |
| `build/web/main.dart.js` | Código compilado |
| `build/web/assets/` | Recursos (fuentes, imágenes, etc.) |
| `build/web/flutter_bootstrap.js` | Arranque Flutter web |

Comprobar:

```bash
test -f build/web/index.html && echo "OK: build/web lista"
ls -la build/web | head
```

### Probar en local (opcional)

```bash
cd build/web
python3 -m http.server 8080
```

Abrir `http://localhost:8080` (o el puerto que indique el servidor).

> `build/` está en `.gitignore`: **no se sube a Git**. Netlify (o tú en local) vuelve a ejecutar `flutter build web` en cada despliegue.

### Si falla el build

```bash
flutter clean
flutter pub get
flutter build web --release
```

---

## 2. Desplegar en Netlify

### A) Netlify construye solo (recomendado tras `git push`)

En el panel de Netlify:

| Tipo de repo | Base directory |
|--------------|----------------|
| `aris-flutter` (solo app) | vacío o `.` |
| Monorepo `aris_flutter_backend` | `aris_flutter_v0.22` |

El archivo `netlify.toml` ya define:

- **Build command:** `bash scripts/netlify-build.sh` (equivale a `flutter pub get` + `flutter build web --release`)
- **Publish directory:** `build/web`

Tras push a `main`, Netlify genera `build/web` en sus servidores y publica.

### B) Deploy manual desde tu máquina (sin build en Netlify)

Primero genera `build/web` (sección 1), luego:

```bash
npx netlify-cli deploy --prod --dir=build/web --no-build
```

Ejecutar desde la carpeta donde está `netlify.toml` (normalmente `aris_flutter_v0.22`).

---

## 3. Git: commit, tag y push (código fuente)

Sustituye `v0.48.XX` y el mensaje por la versión real.

```bash
cd /Users/jose/proyectos/aris_flutter_backend/aris_flutter_v0.22

echo "=== 1. Estado ==="
git status --short

echo "=== 2. Validación ==="
dart analyze
flutter build web --release

echo "=== 3. Commit (solo código; sin build/web) ==="
git add lib/ test/ pubspec.yaml pubspec.lock netlify.toml scripts/
# Ajusta rutas si tocaste más archivos:
# git add -A
git status --short

git commit -m "v0.48.XX Título breve del cambio"

echo "=== 4. Tag ==="
git tag -a v0.48.XX -m "v0.48.XX Título breve del cambio"

echo "=== 5. Push ==="
git push origin main
git push origin v0.48.XX

echo "=== 6. Hecho ==="
git log --oneline -1
git tag --list "v0.48.XX"
```

### Monorepo backend (opcional)

Si también quieres registrar el puntero del submódulo en `aris_flutter_backend`:

```bash
cd /Users/jose/proyectos/aris_flutter_backend
git add aris_flutter_v0.22 docs/
git commit -m "chore: puntero Flutter v0.48.XX"
git push origin rebuild-backend-minimal-v047
```

---

## 4. Resumen rápido

| Objetivo | Comando clave |
|----------|----------------|
| Crear carpeta web | `flutter build web --release` → `build/web/` |
| Probar local | `python3 -m http.server 8080` dentro de `build/web` |
| Subir app a GitHub | `git push origin main` + `git push origin TAG` |
| Netlify automático | Push a `main` (Netlify ejecuta el build) |
| Netlify manual | `netlify deploy --prod --dir=build/web --no-build` |
