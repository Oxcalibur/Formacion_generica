import os
import sys
import subprocess

# --- CONFIGURACIÓN ---
# Carpetas y ficheros que no deben ser modificados por la fusión con main 
# (se mantiene la versión de la rama destino/local)
PROTECTED_PATHS = ["knowledge_base", "images", "data/puntuaciones.json"]
SCRIPT_NAME = os.path.basename(__file__)

def run_cmd(cmd, exit_on_error=False):
    """Ejecuta un comando de shell y devuelve la salida."""
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            check=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        if exit_on_error:
            print(f"❌ Error crítico ejecutando '{cmd}': {e.stderr}")
            sys.exit(1)
        # Si no es crítico, lanzamos la excepción para que la maneje el llamador
        raise e

def get_branches():
    """Obtiene la lista de ramas locales."""
    try:
        raw = run_cmd("git branch --format='%(refname:short)'")
        # Filtramos líneas vacías por seguridad
        return [b.strip() for b in raw.split('\n') if b.strip()]
    except Exception:
        return []

def path_exists_in_head(path):
    """Verifica si un archivo o carpeta existe en el HEAD actual (rama actual)."""
    result = subprocess.run(
        f"git rev-parse --verify HEAD:{path}", 
        shell=True, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE
    )
    return result.returncode == 0

def resolve_conflicts_in_protected_paths():
    """
    Intenta resolver conflictos automáticamente:
    1. Si es ruta protegida: Se queda con la versión local (HEAD/ours).
    2. Si NO es ruta protegida: Se queda con la versión de main (theirs).
    """
    try:
        status = run_cmd("git status --porcelain")
    except Exception:
        return False

    if not status:
        return True # No hay conflictos pendientes

    lines = status.split('\n')
    unmerged_files = []
    
    # Identificar archivos no fusionados (UU, AA, etc.)
    for line in lines:
        if line[:2] in ['UU', 'AA', 'UD', 'DU', 'DD', 'AU', 'UA']:
            unmerged_files.append(line[3:].strip())

    if not unmerged_files:
        return True # No se detectaron archivos unmerged estándar

    print("   ⚔️  Resolviendo conflictos...")
    for file_path in unmerged_files:
        is_protected = False
        for protected in PROTECTED_PATHS:
            # Comprobamos si el archivo empieza con la ruta protegida
            if file_path.startswith(protected):
                is_protected = True
                break
        
        if is_protected:
            # Protegido: Mantenemos nuestra versión (Client/Ours)
            try:
                run_cmd(f"git checkout --ours -- {file_path}")
                run_cmd(f"git add {file_path}")
                print(f"      🛡️ Protegido (Mantiene Local): {file_path}")
            except Exception as e:
                print(f"   ⚠️ Error restaurando {file_path}: {e}")
                return False
        else:
            # No protegido: Sobreescribimos con Main (Theirs)
            try:
                run_cmd(f"git checkout --theirs -- {file_path}")
                run_cmd(f"git add {file_path}")
                print(f"      ⚡ No protegido (Sobreescribe con Main): {file_path}")
            except Exception as e:
                print(f"   ⚠️ Error aplicando main en {file_path}: {e}")
                return False

    return True

def main():
    print(f"--- Gestor de Actualización de Ramas ({SCRIPT_NAME}) ---")
    
    print("Cambiando a 'main' y actualizando...")
    try:
        run_cmd("git checkout main", exit_on_error=True)
        run_cmd("git pull origin main")
    except Exception as e:
        print(f"Error actualizando main: {e}")
        sys.exit(1)

    print("\n" + "-"*30)
    response = input("¿Deseas crear una nueva rama desde main? (s/n): ").strip().lower()
    if response == 's':
        new_branch = input("Introduce el nombre de la nueva rama: ").strip()
        if new_branch:
            if new_branch in get_branches():
                print(f"⚠️ La rama '{new_branch}' ya existe.")
            else:
                run_cmd(f"git checkout -b {new_branch}")
                print(f"✅ Rama '{new_branch}' creada y activa.")
                run_cmd("git checkout main")

    branches = get_branches()
    print("\n" + "-"*30)
    
    ramas_a_procesar = [b for b in branches if b != "main"]
    print(f"Iniciando actualización de {len(ramas_a_procesar)} ramas (excluyendo main)...")

    for branch in ramas_a_procesar:
        print(f"\n🔹 Procesando rama: {branch}")
        try: 
            run_cmd(f"git checkout '{branch}'")
        except Exception as e:
            print(f"   ❌ No se pudo cambiar a la rama '{branch}'")
            if hasattr(e, 'stderr'):
                print(f"      Error: {e.stderr}")
            continue

        print(f"   Fusionando 'main' en '{branch}'...")
        proc = subprocess.run(
            "git merge main --no-commit", 
            shell=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True
        )
        
        if proc.returncode != 0:
            if "Already up to date" in proc.stdout:
                print(f"   ✅ La rama '{branch}' ya está actualizada.")
            else:
                print("   ⚠️ Se detectaron conflictos. Intentando resolver automáticamente...")
                if not resolve_conflicts_in_protected_paths():
                    print(f"   ❌ No se pudo resolver automáticamente. Abortando fusión en '{branch}'.")
                    run_cmd("git merge --abort")
                    continue
                else:
                    print("   ✅ Conflictos en rutas protegidas resueltos.")

        # Asegurar protección incluso si el merge fue limpio
        for path in PROTECTED_PATHS:
            if path_exists_in_head(path):
                try:
                    run_cmd(f"git checkout HEAD -- {path}")
                    if os.path.exists(path): 
                        run_cmd(f"git add {path}")
                except Exception: 
                    pass
        
        # --- BLOQUE DE COMMIT Y PUSH ---
        is_merging = os.path.exists(os.path.join(".git", "MERGE_HEAD"))
        check_staged = subprocess.run("git diff --cached --quiet", shell=True)
        has_staged_changes = (check_staged.returncode != 0)

        if has_staged_changes or is_merging:
            try:
                if is_merging:
                    run_cmd(f'git commit -m "Sync with main (Preservando: {", ".join(PROTECTED_PATHS)})"')
                else:
                    run_cmd(f'git commit -m "Update protected paths after sync"')
                    
                print(f"   ✅ Rama '{branch}' fusionada y empaquetada en local.")

                print(f"   🚀 Subiendo rama '{branch}' a GitHub...")
                try:
                    run_cmd(f"git push origin {branch}")
                    print(f"   ☁️  ¡Rama '{branch}' sincronizada en la nube con éxito!")
                except Exception as push_error:
                    print(f"   ❌ Guardado localmente, pero falló la subida a GitHub: {push_error}")

            except Exception as e:
                print(f"   ❌ Error al hacer commit: {e}")
                if os.path.exists(os.path.join(".git", "MERGE_HEAD")):
                    subprocess.run("git merge --abort", shell=True) 
        else:
            print(f"   ℹ️  Sin nuevos commits que empaquetar (actualización limpia/fast-forward).")
            if is_merging:
                 subprocess.run("git merge --abort", shell=True)
                 
            print(f"   🚀 Asegurando actualización en GitHub...")
            subprocess.run(f"git push origin '{branch}'", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"   ☁️  Rama '{branch}' comprobada y online.")

    print("\n" + "-"*30)
    run_cmd("git checkout main")
    print("✅ Proceso completado.")

if __name__ == "__main__":
    main()