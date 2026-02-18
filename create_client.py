import os
import subprocess
import sys

def run_command(command):
    """Ejecuta comandos de Git silenciosamente salvo error."""
    try:
        subprocess.run(command, shell=True, check=True, text=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error al ejecutar: {command}")
        print(f"   Detalle: {e.stderr}")
        sys.exit(1)

def crear_cliente():
    print("\n✨ --- ASISTENTE DE CREACIÓN DE NUEVA INSTANCIA PARA CLIENTE --- ✨\n")

    # 1. DATOS DEL CLIENTE
    nombre_raw = input("1. Nombre del cliente (ej: Iberia, Demo Liderazgo): ")
    # Convertimos a formato URL (ej: demo-liderazgo)
    rama_cliente = nombre_raw.lower().replace(" ", "-")
    
    print(f"   🔹 Se creará la rama: '{rama_cliente}'")
    confirm = input("   ¿Continuar? (s/n): ")
    if confirm.lower() != 's': return

    # 2. GESTIÓN DE GIT
    print("\n⚙️  --- PROCESANDO GIT ---")
    print("   ⏳ Volviendo a main y actualizando...")
    run_command("git checkout main")
    run_command("git pull origin main")
    
    print(f"   ⏳ Creando rama '{rama_cliente}'...")
    # El -B fuerza la creación o reseteo si ya existía localmente
    run_command(f"git checkout -B {rama_cliente}")

    # 3. SUBIDA A LA NUBE
    print("\n🚀 --- SUBIENDO A GITHUB ---")
    run_command("git add .")
    run_command(f'git commit -m "Alta cliente (Rama): {nombre_raw}"')
    
    print("   ⏳ Empujando a la nube...")
    run_command(f"git push --force --set-upstream origin {rama_cliente}")
    print("   ✅ Rama creada y subida a GitHub.")

    # 4. INSTRUCCIONES FINALES
    print(f"\n🎉 --- ¡ÉXITO! RAMA '{rama_cliente}' CREADA ---")
    print("\n📋 ACCIONES REQUERIDAS:")
    print("1. Ve a Google Drive y crea una **NUEVA HOJA DE CÁLCULO** para este cliente.")
    print("2. Dentro de esa hoja, crea una pestaña (worksheet) llamada exactamente `Users`.")
    print(f"3. Comparte la hoja con el rol de 'Editor' a tu email de servicio: `asistente-ia@gen-lang-client-0006409633.iam.gserviceaccount.com`")
    print(f"4. Al desplegar la rama '{rama_cliente}', configura el secreto `spreadsheet` con la URL de esta **NUEVA** hoja.")

if __name__ == "__main__":
    crear_cliente()