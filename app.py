"""
UABE Python - Versão otimizada para hospedagem no Render.com
Backend Flask com UnityPy para extração de Unity Asset Bundles.

Ajustes específicos para o Render:
- Porta lida da variável de ambiente $PORT
- Host definido como 0.0.0.0
- Gunicorn recomendado como servidor WSGI
- Sistema de arquivos efêmero: uploads/exports são temporários
- CORS habilitado para permitir conexão do GitHub Pages se necessário
"""

import os
import io
import zipfile
from pathlib import Path
from flask import Flask, request, jsonify, send_file, abort, render_template
from flask_cors import CORS

from uabe_py import UABEPython

# ====== CONFIGURAÇÃO ======
BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "_uploads"
EXPORT_DIR = BASE_DIR / "_exports"
SESSION_DIR = BASE_DIR / "_session"

UPLOAD_DIR.mkdir(exist_ok=True)
EXPORT_DIR.mkdir(exist_ok=True)
SESSION_DIR.mkdir(exist_ok=True)

# Porta do Render (via variável de ambiente) ou padrão 5000
PORT = int(os.environ.get('PORT', 5000))
HOST = '0.0.0.0'  # Obrigatório no Render

# Origens permitidas para CORS (caso queira conectar do GitHub Pages ou outro frontend)
ALLOWED_ORIGINS = [
    r"http://localhost:\d+",
    r"http://127.0.0.1:\d+",
    r"https?://.*\.github\.io",
    r"https?://.*\.onrender\.com",
    r"https?://.*\.render\.com",
]

# ====== INICIALIZAÇÃO FLASK ======
app = Flask(__name__, template_folder=str(BASE_DIR / "templates"))

# Limite de upload: 1GB (ajuste conforme necessidade)
# Render tem limite de request body de ~100MB no free tier — esteja ciente
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024 * 1024  # 1GB

# Habilita CORS (útil se quiser usar interface externa como GitHub Pages)
CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=True)

# Instância global
uabe_instance = UABEPython()
current_file = None

# ====== PERSISTÊNCIA ROBUSTA DE SESSÃO ======
# O Render pode ter múltiplos workers gunicorn com memória isolada.
# Solução: salvar o bundle atual em um arquivo de NOME FIXO em disco.
# Qualquer worker que receber uma requisição tenta carregar desse arquivo.

CURRENT_BUNDLE_FILE = SESSION_DIR / "current_bundle.bin"
CURRENT_BUNDLE_META = SESSION_DIR / "current_bundle_meta.json"

def _save_session(file_path: str, original_filename: str = ""):
    """
    Salva o bundle atual em disco com nome fixo para que QUALQUER worker
    possa recarregá-lo. Copia o arquivo original para um local conhecido.
    """
    try:
        import shutil
        import json
        
        # Copia o bundle para o arquivo fixo de sessão
        shutil.copy2(file_path, str(CURRENT_BUNDLE_FILE))
        
        # Salva metadados
        meta = {
            'original_filename': original_filename,
            'source_path': file_path,
            'saved_at': str(__import__('datetime').datetime.now()),
            'size_bytes': os.path.getsize(file_path)
        }
        CURRENT_BUNDLE_META.write_text(json.dumps(meta, indent=2), encoding='utf-8')
        
        print(f"💾 Sessão salva em disco: {CURRENT_BUNDLE_FILE}")
        return True
    except Exception as e:
        print(f"⚠️ ERRO ao salvar sessão: {e}")
        import traceback
        traceback.print_exc()
        return False

def _clear_session():
    """Remove todos os arquivos de sessão"""
    try:
        if CURRENT_BUNDLE_FILE.exists():
            CURRENT_BUNDLE_FILE.unlink()
        if CURRENT_BUNDLE_META.exists():
            CURRENT_BUNDLE_META.unlink()
        print("🗑️ Sessão limpa")
    except Exception as e:
        print(f"Aviso ao limpar sessão: {e}")

def ensure_bundle_loaded() -> bool:
    """
    Garante que o bundle está carregado. Se não estiver na memória,
    tenta carregar do arquivo fixo em disco. Funciona entre workers.
    """
    global current_file
    
    # Já está carregado e o arquivo existe
    if current_file and os.path.exists(current_file):
        return True
    
    # Tenta 1: arquivo salvo pela própria instância anteriormente
    if current_file and not os.path.exists(current_file):
        current_file = None
    
    # Tenta 2: carregar do arquivo fixo de sessão em disco
    if CURRENT_BUNDLE_FILE.exists() and CURRENT_BUNDLE_FILE.stat().st_size > 0:
        try:
            print(f"♻️ Tentando recarregar bundle do arquivo fixo: {CURRENT_BUNDLE_FILE}")
            if uabe_instance.load_file(str(CURRENT_BUNDLE_FILE)):
                current_file = str(CURRENT_BUNDLE_FILE)
                print(f"✅ Bundle recarregado com sucesso! Assets: {len(uabe_instance.assets)}")
                return True
            else:
                print("❌ Falha ao carregar o arquivo de sessão")
        except Exception as e:
            print(f"❌ Exceção ao recarregar: {e}")
    
    print("⚠️ Nenhum bundle carregado na memória e nenhum arquivo de sessão encontrado")
    return False

def _get_debug_info() -> dict:
    """Retorna informações de diagnóstico da instância atual"""
    import json
    
    meta = {}
    if CURRENT_BUNDLE_META.exists():
        try:
            meta = json.loads(CURRENT_BUNDLE_META.read_text(encoding='utf-8'))
        except:
            pass
    
    return {
        'pid': os.getpid(),
        'current_file_in_memory': current_file,
        'current_file_exists': os.path.exists(current_file) if current_file else False,
        'session_file_exists': CURRENT_BUNDLE_FILE.exists(),
        'session_file_size': CURRENT_BUNDLE_FILE.stat().st_size if CURRENT_BUNDLE_FILE.exists() else 0,
        'assets_loaded': len(uabe_instance.assets),
        'meta': meta,
        'session_dir_contents': [str(f.name) for f in SESSION_DIR.iterdir()] if SESSION_DIR.exists() else [],
        'upload_dir_contents': [str(f.name) for f in UPLOAD_DIR.iterdir()] if UPLOAD_DIR.exists() else [],
    }


# ====== UTILITÁRIOS ======
def _cleanup_old_files():
    """Remove arquivos antigos para não encher o disco efêmero"""
    try:
        # Limpa uploads
        for f in UPLOAD_DIR.glob("*"):
            try:
                f.unlink()
            except:
                pass
        # Limpa exports
        import shutil
        for d in EXPORT_DIR.glob("*"):
            try:
                if d.is_dir():
                    shutil.rmtree(d)
                else:
                    d.unlink()
            except:
                pass
    except:
        pass


# ====== ROTAS ======

@app.route('/')
def index():
    """Interface web principal"""
    summary = uabe_instance.get_summary() if current_file else None
    return render_template('index.html', summary=summary)


@app.route('/api/health', methods=['GET'])
def api_health():
    """Health check"""
    return jsonify({
        'status': 'online',
        'service': 'uabe-python-render',
        'version': '1.0.0-render'
    })


@app.route('/api/upload', methods=['POST'])
def api_upload():
    global current_file
    
    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400
    
    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'Nome de arquivo vazio'}), 400
    
    # Limpa arquivos anteriores (sistema de arquivos efêmero)
    _cleanup_old_files()
    
    filename = file.filename
    save_path = UPLOAD_DIR / filename
    
    counter = 1
    while save_path.exists():
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        save_path = UPLOAD_DIR / f"{stem}_{counter}{suffix}"
        counter += 1
    
    file.save(str(save_path))
    
    if uabe_instance.load_file(str(save_path)):
        current_file = str(save_path)
        _save_session(current_file, filename)  # Persiste para outros workers (arquivo fixo em disco)
        return jsonify({
            'success': True,
            'summary': uabe_instance.get_summary(),
            'file': filename
        })
    else:
        try:
            save_path.unlink()
        except:
            pass
        return jsonify({'error': 'Não foi possível carregar este arquivo como Asset Bundle Unity'}), 400


@app.route('/api/assets', methods=['GET'])
def api_assets():
    if not ensure_bundle_loaded():
        return jsonify({'assets': [], 'error': 'Nenhum arquivo carregado'}), 400
    
    asset_type = request.args.get('type', '').strip()
    search = request.args.get('search', '').strip().lower()
    
    if asset_type:
        assets = uabe_instance.get_assets_by_type(asset_type)
    else:
        assets = uabe_instance.assets
    
    if search:
        assets = [
            a for a in assets
            if search in a.name.lower() or
               search in a.type.lower() or
               search in str(a.path_id) or
               search in a.container.lower()
        ]
    
    return jsonify({
        'assets': [a.to_dict() for a in assets],
        'total': len(assets)
    })


@app.route('/api/types', methods=['GET'])
def api_types():
    if not ensure_bundle_loaded():
        return jsonify({'types': []}), 400
    return jsonify({'types': uabe_instance.get_all_types()})


@app.route('/api/summary', methods=['GET'])
def api_summary():
    if not ensure_bundle_loaded():
        return jsonify({'error': 'Nenhum arquivo carregado'}), 400
    return jsonify(uabe_instance.get_summary())


@app.route('/api/asset/<int:path_id>', methods=['GET'])
def api_asset_details(path_id):
    if not ensure_bundle_loaded():
        return jsonify({'error': 'Nenhum arquivo carregado'}), 400
    
    details = uabe_instance.get_asset_details(path_id)
    if not details:
        return jsonify({'error': 'Asset não encontrado'}), 404
    return jsonify(details)


@app.route('/api/preview/<int:path_id>', methods=['GET'])
def api_preview(path_id):
    if not ensure_bundle_loaded():
        abort(404)
    
    preview_bytes = uabe_instance.get_texture_preview(path_id, max_size=512)
    if not preview_bytes:
        abort(404)
    
    return send_file(
        io.BytesIO(preview_bytes),
        mimetype='image/png',
        download_name=f"preview_{path_id}.png"
    )


@app.route('/api/extract/<int:path_id>', methods=['GET'])
def api_extract_one(path_id):
    if not ensure_bundle_loaded():
        return jsonify({'error': 'Nenhum arquivo carregado'}), 400
    
    out_dir = EXPORT_DIR / f"single_{path_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    result = uabe_instance.extract_asset(path_id, str(out_dir))
    if not result or not os.path.exists(result):
        return jsonify({'error': 'Falha na extração'}), 500
    
    return send_file(result, as_attachment=True)


@app.route('/api/extract-all', methods=['POST'])
def api_extract_all():
    if not ensure_bundle_loaded():
        return jsonify({'error': 'Nenhum arquivo carregado'}), 400
    
    data = request.get_json(silent=True) or {}
    types = data.get('types')
    
    base_name = Path(current_file).stem
    out_dir = EXPORT_DIR / f"extract_{base_name}"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    results = uabe_instance.extract_all(str(out_dir), types)
    
    zip_path = EXPORT_DIR / f"{base_name}_exported.zip"
    with zipfile.ZipFile(str(zip_path), 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(str(out_dir)):
            for file in files:
                full_path = os.path.join(root, file)
                arcname = os.path.relpath(full_path, str(out_dir))
                zf.write(full_path, arcname)
    
    total = sum(len(v) for v in results.values())
    return jsonify({
        'success': True,
        'total_files': total,
        'per_type': {k: len(v) for k, v in results.items()},
        'zip_filename': zip_path.name
    })


@app.route('/api/download-zip/<filename>', methods=['GET'])
def api_download_zip(filename):
    zip_path = EXPORT_DIR / filename
    if not zip_path.exists():
        abort(404)
    return send_file(str(zip_path), as_attachment=True)


@app.route('/api/replace-texture/<int:path_id>', methods=['POST'])
def api_replace_texture(path_id):
    """Substitui uma Texture2D por um arquivo PNG enviado"""
    global current_file
    
    if not ensure_bundle_loaded():
        return jsonify({'error': 'Nenhum arquivo carregado'}), 400
    
    if 'png' not in request.files:
        return jsonify({'error': 'Arquivo PNG não enviado (campo esperado: "png")'}), 400
    
    png_file = request.files['png']
    if not png_file.filename:
        return jsonify({'error': 'Nome de arquivo PNG vazio'}), 400
    
    # Verifica se o asset é uma textura
    asset_info = uabe_instance.get_asset_by_path_id(path_id)
    if not asset_info:
        return jsonify({'error': 'Asset não encontrado'}), 404
    
    if asset_info.type not in ['Texture2D', 'Sprite']:
        return jsonify({'error': f'Asset do tipo {asset_info.type} não é uma textura substituível'}), 400
    
    try:
        from PIL import Image
        
        # Abre a imagem diretamente do upload
        pil_img = Image.open(png_file.stream)
        
        # Validação básica
        if pil_img.size[0] == 0 or pil_img.size[1] == 0:
            return jsonify({'error': 'Imagem PNG inválida'}), 400
        
        # Executa a substituição
        success = uabe_instance.replace_texture(path_id, pil_img)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Textura substituída com sucesso',
                'asset': {
                    'path_id': path_id,
                    'type': asset_info.type,
                    'name': asset_info.name
                },
                'new_image': {
                    'width': pil_img.size[0],
                    'height': pil_img.size[1],
                    'mode': pil_img.mode
                }
            })
        else:
            return jsonify({'error': 'Falha ao substituir textura (ver logs do servidor)'}), 500
            
    except Exception as e:
        return jsonify({'error': f'Erro ao processar PNG: {str(e)}'}), 500


@app.route('/api/download-modified', methods=['GET'])
def api_download_modified():
    """Gera e baixa o bundle completo com as modificações aplicadas"""
    global current_file
    
    if not ensure_bundle_loaded():
        return jsonify({'error': 'Nenhum arquivo carregado'}), 400
    
    try:
        import time
        base_name = Path(current_file).stem
        modified_filename = f"{base_name}_modified.unity3d"
        output_path = EXPORT_DIR / modified_filename
        
        saved_path = uabe_instance.save_modified_bundle(str(output_path))
        
        if saved_path and os.path.exists(saved_path):
            return send_file(
                saved_path,
                as_attachment=True,
                download_name=modified_filename,
                mimetype='application/octet-stream'
            )
        else:
            return jsonify({'error': 'Falha ao gerar arquivo modificado'}), 500
            
    except Exception as e:
        return jsonify({'error': f'Erro ao salvar: {str(e)}'}), 500


@app.route('/api/debug/status', methods=['GET'])
def api_debug_status():
    """Endpoint de diagnóstico — acessível para ver o estado da instância"""
    return jsonify(_get_debug_info())


@app.route('/api/unload', methods=['POST'])
def api_unload():
    global current_file
    uabe_instance.__init__()
    current_file = None
    _clear_session()
    _cleanup_old_files()
    return jsonify({'success': True})


# ====== INICIALIZAÇÃO ======
if __name__ == '__main__':
    print(f"🚀 UABE Python (Render Edition) iniciando...")
    print(f"📡 Host: {HOST} | Porta: {PORT}")
    print(f"📂 Upload dir: {UPLOAD_DIR}")
    # Para desenvolvimento local:
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
else:
    # Quando executado via gunicorn (produção no Render):
    print(f"✅ UABE Python carregado via gunicorn. Porta: {PORT}")
