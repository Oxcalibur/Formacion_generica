import hashlib
import json
import os
import pandas as pd
import streamlit as st
try:
    from streamlit_gsheets import GSheetsConnection
except ImportError:
    GSheetsConnection = None
from config import SECURITY_CONFIG

class AuthManager:
    def __init__(self):
        self._initialize_db()

    def _hash_password(self, password):
        """Genera un hash SHA-256 de la contraseña."""
        return hashlib.sha256(password.encode()).hexdigest()

    def _initialize_db(self):
        """Crea la hoja con usuarios por defecto o actualiza credenciales."""
        # Definir credenciales base
        default_creds = {
            "admin": "admin123",
            "empleado": "olivia2024"
        }
        
        data = self._load_db()
            
        updated = False
        # Verificar/Crear usuarios por defecto
        for user, pwd in default_creds.items():
            pwd_hash = self._hash_password(pwd)
            if user not in data:
                data[user] = {
                    "password_hash": pwd_hash,
                    "score": 0,
                    "active_sessions": 0,
                    "role": "admin" if user == "admin" else "user"
                }
                updated = True
            elif data[user].get("password_hash") != pwd_hash:
                # Actualizar contraseña si ha cambiado en código
                data[user]["password_hash"] = pwd_hash
                updated = True
                
        if updated:
            self._save_db(data)

    def _load_db(self):
        """Carga la base de datos de usuarios desde Google Sheets."""
        if GSheetsConnection is None:
            return {}
        try:
            conn = st.connection("gsheets", type=GSheetsConnection)
            df = conn.read(worksheet="Users", ttl=0)
            if df.empty:
                return {}
            df = df.dropna(how="all")
            if "username" not in df.columns:
                return {}
            return df.set_index("username").to_dict(orient="index")
        except Exception:
            return {}

    def _save_db(self, data):
        """Guarda la base de datos de usuarios en Google Sheets."""
        if GSheetsConnection is None:
            return
        try:
            df = pd.DataFrame.from_dict(data, orient="index")
            df.index.name = "username"
            df.reset_index(inplace=True)
            conn = st.connection("gsheets", type=GSheetsConnection)
            conn.update(worksheet="Users", data=df)
        except Exception as e:
            st.error(f"Error guardando en Google Sheets: {e}")

    def authenticate(self, username, password):
        """Verifica las credenciales del usuario."""
        data = self._load_db()
        user = data.get(username)
        
        if not user:
            return False
            
        # Verificar hash
        input_hash = self._hash_password(password)
        stored_hash = user.get("password_hash")
        
        # Compatibilidad: Si no hay hash (formato antiguo), actualizamos
        if not stored_hash and "password" in user:
            # Nota: Esto es solo para migración si fuera necesario
            return False 
            
        return input_hash == stored_hash

    def get_user_progress(self, username):
        """Obtiene el progreso actual del usuario."""
        data = self._load_db()
        user = data.get(username, {})
        return {
            "score": user.get("score", 0),
            "active_sessions": user.get("active_sessions", 0)
        }

    def update_user_progress(self, username, score=None, increment_session=False):
        """Actualiza la puntuación y sesiones del usuario."""
        data = self._load_db()
        
        if username not in data:
            # Si el usuario no existe, lo creamos
            data[username] = {"score": 0, "active_sessions": 0}
            
        if score is not None:
            data[username]["score"] = score
            
        if increment_session:
            data[username]["active_sessions"] = data[username].get("active_sessions", 0) + 1
            
        self._save_db(data)

# Instancia global para usar en la app
auth_manager = AuthManager()