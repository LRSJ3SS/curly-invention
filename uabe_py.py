"""
UABE Python - Adaptacao do Unity Asset Bundle Extractor usando UnityPy
Funcionalidades:
- Carregar arquivos .unity3d, .bundle, .assets, etc.
- Listar todos os assets internos
- Extrair Texturas (Texture2D/Sprite) como PNG
- Extrair TextAssets como arquivos .txt
- Extrair AudioClips como .wav/.ogg
- Extrair Meshes como .obj
- Visualizar informacoes detalhadas dos assets
"""

import os
import io
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

import UnityPy
from UnityPy.enums import ClassIDType
from PIL import Image


@dataclass
class AssetInfo:
    """Informacoes de um asset dentro do bundle"""
    path_id: int
    type: str
    name: str
    size: int
    container: str
    index: int
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class UABEPython:
    """Classe principal para manipulacao de Asset Bundles Unity"""
    
    def __init__(self):
        self.env = None
        self.file_path = None
        self.assets: List[AssetInfo] = []
        self.objects_map: Dict[int, Any] = {}
        
    def load_file(self, file_path: str) -> bool:
        """Carrega um arquivo de Asset Bundle Unity"""
        try:
            self.file_path = file_path
            self.env = UnityPy.load(file_path)
            self._scan_assets()
            return True
        except Exception as e:
            print(f"Erro ao carregar arquivo: {e}")
            return False
    
    def _scan_assets(self):
        """Escaneia todos os assets dentro do bundle carregado"""
        self.assets = []
        self.objects_map = {}
        
        if not self.env:
            return
        
        for idx, obj in enumerate(self.env.objects):
            try:
                obj_type = obj.type.name if hasattr(obj.type, 'name') else str(obj.type)
                asset_name = ""
                container = ""
                
                # Tenta obter o nome do asset
                try:
                    data = obj.read()
                    if hasattr(data, 'm_Name'):
                        asset_name = data.m_Name or ""
                except:
                    pass
                
                # Tenta obter o container (caminho interno)
                try:
                    if obj.assets_file and hasattr(obj.assets_file, 'container'):
                        for path, obj_ref in obj.assets_file.container.items():
                            if obj_ref.path_id == obj.path_id:
                                container = path
                                break
                except:
                    pass
                
                info = AssetInfo(
                    path_id=obj.path_id,
                    type=obj_type,
                    name=asset_name,
                    size=obj.byte_size if hasattr(obj, 'byte_size') else 0,
                    container=container,
                    index=idx
                )
                
                self.assets.append(info)
                self.objects_map[obj.path_id] = obj
                
            except Exception as e:
                print(f"Aviso: nao foi possivel ler asset {obj.path_id}: {e}")
                continue
    
    def get_assets_by_type(self, type_name: str) -> List[AssetInfo]:
        """Retorna assets filtrados por tipo"""
        return [a for a in self.assets if a.type.lower() == type_name.lower()]
    
    def get_all_types(self) -> List[str]:
        """Retorna lista de todos os tipos de assets presentes"""
        types = sorted(set(a.type for a in self.assets))
        return types
    
    def get_asset_by_path_id(self, path_id: int) -> Optional[AssetInfo]:
        """Busca um asset pelo Path ID"""
        for a in self.assets:
            if a.path_id == path_id:
                return a
        return None
    
    def extract_texture(self, path_id: int, output_dir: str) -> Optional[str]:
        """Extrai uma textura (Texture2D/Sprite) como PNG"""
        obj = self.objects_map.get(path_id)
        if not obj:
            return None
        
        try:
            data = obj.read()
            
            # Para Sprite, pega a textura associada
            if obj.type == ClassIDType.Sprite:
                if hasattr(data, 'm_RD') and hasattr(data.m_RD, 'texture'):
                    tex_obj = data.m_RD.texture
                    if tex_obj:
                        data = tex_obj.read()
                    else:
                        return None
                else:
                    return None
            
            if not hasattr(data, 'image'):
                return None
            
            os.makedirs(output_dir, exist_ok=True)
            name = data.m_Name if hasattr(data, 'm_Name') and data.m_Name else f"texture_{path_id}"
            name = self._sanitize_filename(name)
            output_path = os.path.join(output_dir, f"{name}.png")
            
            img = data.image
            if img:
                img.save(output_path, "PNG")
                return output_path
            
        except Exception as e:
            print(f"Erro ao extrair textura {path_id}: {e}")
        
        return None
    
    def extract_text_asset(self, path_id: int, output_dir: str) -> Optional[str]:
        """Extrai um TextAsset como arquivo de texto"""
        obj = self.objects_map.get(path_id)
        if not obj:
            return None
        
        try:
            data = obj.read()
            if not hasattr(data, 'm_Script'):
                return None
            
            os.makedirs(output_dir, exist_ok=True)
            name = data.m_Name if hasattr(data, 'm_Name') and data.m_Name else f"text_{path_id}"
            name = self._sanitize_filename(name)
            
            # Determina extensao baseado no conteudo ou nome
            ext = ".txt"
            script_str = data.m_Name if isinstance(data.m_Name, str) else ""
            if script_str.endswith('.json'):
                ext = ".json"
            elif script_str.endswith('.xml'):
                ext = ".xml"
            elif script_str.endswith('.bytes'):
                ext = ".bytes"
            elif script_str.endswith('.csv'):
                ext = ".csv"
            
            output_path = os.path.join(output_dir, f"{name}{ext}")
            
            script_data = data.m_Script
            if isinstance(script_data, str):
                script_data = script_data.encode('utf-8', errors='surrogateescape')
            
            with open(output_path, 'wb') as f:
                f.write(script_data)
            
            return output_path
            
        except Exception as e:
            print(f"Erro ao extrair TextAsset {path_id}: {e}")
        
        return None
    
    def extract_audio(self, path_id: int, output_dir: str) -> Optional[str]:
        """Extrai um AudioClip"""
        obj = self.objects_map.get(path_id)
        if not obj:
            return None
        
        try:
            data = obj.read()
            if not hasattr(data, 'm_AudioData'):
                return None
            
            os.makedirs(output_dir, exist_ok=True)
            name = data.m_Name if hasattr(data, 'm_Name') and data.m_Name else f"audio_{path_id}"
            name = self._sanitize_filename(name)
            
            # Tenta obter extensao do audio
            ext = ".wav"
            try:
                compression = getattr(data, 'm_CompressionFormat', None)
                if compression == 1:  # Vorbis
                    ext = ".ogg"
                elif compression == 2:  # ADPCM
                    ext = ".wav"
            except:
                pass
            
            output_path = os.path.join(output_dir, f"{name}{ext}")
            
            audio_data = data.m_AudioData
            if isinstance(audio_data, str):
                audio_data = audio_data.encode('latin-1')
            
            with open(output_path, 'wb') as f:
                f.write(audio_data)
            
            return output_path
            
        except Exception as e:
            print(f"Erro ao extrair AudioClip {path_id}: {e}")
        
        return None
    
    def extract_mesh(self, path_id: int, output_dir: str) -> Optional[str]:
        """Extrai um Mesh como arquivo OBJ"""
        obj = self.objects_map.get(path_id)
        if not obj:
            return None
        
        try:
            data = obj.read()
            os.makedirs(output_dir, exist_ok=True)
            name = data.m_Name if hasattr(data, 'm_Name') and data.m_Name else f"mesh_{path_id}"
            name = self._sanitize_filename(name)
            output_path = os.path.join(output_dir, f"{name}.obj")
            
            # Tenta usar o exportador nativo do UnityPy
            if hasattr(data, 'export'):
                exported = data.export()
                if exported:
                    with open(output_path, 'wb') as f:
                        if isinstance(exported, str):
                            f.write(exported.encode('utf-8'))
                        else:
                            f.write(exported)
                    return output_path
            
            # Fallback: gera OBJ manualmente se tiver vertices
            if hasattr(data, 'm_Vertices') and hasattr(data, 'm_Normals'):
                verts = data.m_Vertices
                normals = getattr(data, 'm_Normals', [])
                uvs = getattr(data, 'm_UV0', [])
                triangles = getattr(data, 'm_Indices', [])
                
                with open(output_path, 'w') as f:
                    f.write(f"# Mesh: {name}\n")
                    f.write(f"o {name}\n")
                    
                    for i in range(0, len(verts), 3):
                        f.write(f"v {verts[i]} {verts[i+1]} {verts[i+2]}\n")
                    
                    for i in range(0, len(normals), 3):
                        f.write(f"vn {normals[i]} {normals[i+1]} {normals[i+2]}\n")
                    
                    for i in range(0, len(uvs), 2):
                        f.write(f"vt {uvs[i]} {uvs[i+1]}\n")
                    
                    if triangles:
                        for i in range(0, len(triangles), 3):
                            f.write(f"f {triangles[i]+1}/{triangles[i]+1}/{triangles[i]+1} ")
                            f.write(f"{triangles[i+1]+1}/{triangles[i+1]+1}/{triangles[i+1]+1} ")
                            f.write(f"{triangles[i+2]+1}/{triangles[i+2]+1}/{triangles[i+2]+1}\n")
                
                return output_path
            
        except Exception as e:
            print(f"Erro ao extrair Mesh {path_id}: {e}")
        
        return None
    
    def extract_asset(self, path_id: int, output_dir: str) -> Optional[str]:
        """Extrai um asset baseado no seu tipo"""
        info = self.get_asset_by_path_id(path_id)
        if not info:
            return None
        
        type_lower = info.type.lower()
        
        if type_lower in ['texture2d', 'sprite']:
            return self.extract_texture(path_id, os.path.join(output_dir, "Textures"))
        elif type_lower == 'textasset':
            return self.extract_text_asset(path_id, os.path.join(output_dir, "TextAssets"))
        elif type_lower == 'audioclip':
            return self.extract_audio(path_id, os.path.join(output_dir, "Audio"))
        elif type_lower == 'mesh':
            return self.extract_mesh(path_id, os.path.join(output_dir, "Meshes"))
        else:
            # Tenta exportacao generica
            return self._extract_generic(path_id, output_dir)
    
    def _extract_generic(self, path_id: int, output_dir: str) -> Optional[str]:
        """Tentativa de extracao generica para outros tipos"""
        obj = self.objects_map.get(path_id)
        if not obj:
            return None
        
        try:
            data = obj.read()
            os.makedirs(output_dir, exist_ok=True)
            name = getattr(data, 'm_Name', None) or f"asset_{path_id}"
            name = self._sanitize_filename(name)
            
            # Tenta metodo export()
            if hasattr(data, 'export'):
                exported = data.export()
                if exported:
                    output_path = os.path.join(output_dir, f"{name}.bin")
                    with open(output_path, 'wb') as f:
                        if isinstance(exported, str):
                            f.write(exported.encode('utf-8', errors='surrogateescape'))
                        else:
                            f.write(exported)
                    return output_path
            
            # Salva como JSON/dump se possivel
            output_path = os.path.join(output_dir, f"{name}.json")
            try:
                dump = self._object_to_dict(data)
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(dump, f, indent=2, default=str, ensure_ascii=False)
                return output_path
            except:
                pass
            
        except Exception as e:
            print(f"Erro na extracao generica {path_id}: {e}")
        
        return None
    
    def _object_to_dict(self, obj, max_depth: int = 2) -> Any:
        """Converte um objeto Unity em dicionario para inspecao"""
        if max_depth <= 0:
            return str(obj)
        
        if isinstance(obj, (int, float, str, bool, type(None))):
            return obj
        
        if isinstance(obj, (list, tuple)):
            return [self._object_to_dict(item, max_depth - 1) for item in obj[:100]]
        
        if isinstance(obj, dict):
            return {str(k): self._object_to_dict(v, max_depth - 1) for k, v in list(obj.items())[:100]}
        
        result = {}
        for attr in dir(obj):
            if attr.startswith('_') or attr.startswith('m_Editor'):
                continue
            try:
                val = getattr(obj, attr)
                if callable(val):
                    continue
                result[attr] = self._object_to_dict(val, max_depth - 1)
            except:
                continue
        
        return result if result else str(obj)
    
    def get_asset_details(self, path_id: int) -> Optional[Dict[str, Any]]:
        """Retorna detalhes completos de um asset em formato JSON"""
        obj = self.objects_map.get(path_id)
        if not obj:
            return None
        
        info = self.get_asset_by_path_id(path_id)
        if not info:
            return None
        
        try:
            data = obj.read()
            details = info.to_dict()
            details['properties'] = self._object_to_dict(data, max_depth=3)
            return details
        except Exception as e:
            return {
                **info.to_dict(),
                'error': str(e)
            }
    
    def extract_all(self, output_dir: str, types: Optional[List[str]] = None) -> Dict[str, List[str]]:
        """Extrai todos os assets (ou tipos especificos) para um diretorio"""
        results = {}
        
        for asset in self.assets:
            if types and asset.type.lower() not in [t.lower() for t in types]:
                continue
            
            extracted = self.extract_asset(asset.path_id, output_dir)
            if extracted:
                asset_type = asset.type
                if asset_type not in results:
                    results[asset_type] = []
                results[asset_type].append(extracted)
        
        return results
    
    def get_texture_preview(self, path_id: int, max_size: int = 256) -> Optional[bytes]:
        """Retorna bytes PNG de uma miniatura da textura para preview"""
        obj = self.objects_map.get(path_id)
        if not obj:
            return None
        
        try:
            data = obj.read()
            
            if obj.type == ClassIDType.Sprite:
                if hasattr(data, 'm_RD') and hasattr(data.m_RD, 'texture'):
                    tex_obj = data.m_RD.texture
                    if tex_obj:
                        data = tex_obj.read()
                    else:
                        return None
            
            if not hasattr(data, 'image'):
                return None
            
            img = data.image
            if not img:
                return None
            
            # Cria miniatura
            img.thumbnail((max_size, max_size), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
            
        except Exception as e:
            print(f"Erro no preview {path_id}: {e}")
            return None
    
    def replace_texture(self, path_id: int, new_image) -> bool:
        """
        Substitui uma Texture2D por uma nova imagem PIL.
        
        Args:
            path_id: Path ID do asset Texture2D a ser substituído
            new_image: Objeto PIL.Image (deve ser RGBA ou RGB)
        
        Returns:
            True se a substituição foi bem-sucedida
        """
        obj = self.objects_map.get(path_id)
        if not obj:
            print(f"Asset {path_id} não encontrado")
            return False
        
        if obj.type.name not in ['Texture2D', 'Sprite']:
            print(f"Asset {path_id} não é uma textura (tipo: {obj.type.name})")
            return False
        
        try:
            data = obj.read()
            
            # Para Sprite, pegamos a textura associada
            if obj.type.name == 'Sprite':
                if hasattr(data, 'm_RD') and hasattr(data.m_RD, 'texture') and data.m_RD.texture:
                    data = data.m_RD.texture.read()
                else:
                    print("Sprite não tem textura associada")
                    return False
            
            if not hasattr(data, 'image'):
                print("Textura não tem propriedade .image")
                return False
            
            # Garante que a imagem está no modo compatível (RGBA)
            from PIL import Image
            if new_image.mode not in ['RGBA', 'RGB']:
                new_image = new_image.convert('RGBA')
            
            # Atribui a nova imagem
            data.image = new_image
            
            # Salva as alterações no objeto
            data.save()
            
            print(f"✅ Textura {path_id} substituída com sucesso")
            return True
            
        except Exception as e:
            print(f"❌ Erro ao substituir textura {path_id}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def replace_texture_from_file(self, path_id: int, png_file_path: str) -> bool:
        """
        Substitui uma Texture2D a partir de um arquivo PNG.
        
        Args:
            path_id: Path ID do asset Texture2D
            png_file_path: Caminho para o arquivo PNG de substituição
        
        Returns:
            True se bem-sucedido
        """
        from PIL import Image
        
        if not os.path.exists(png_file_path):
            print(f"Arquivo PNG não encontrado: {png_file_path}")
            return False
        
        try:
            pil_img = Image.open(png_file_path)
            return self.replace_texture(path_id, pil_img)
        except Exception as e:
            print(f"Erro ao abrir PNG: {e}")
            return False
    
    def save_modified_bundle(self, output_path: str) -> Optional[str]:
        """
        Salva o bundle completo com todas as modificações aplicadas.
        
        Args:
            output_path: Caminho onde o arquivo modificado será salvo
        
        Returns:
            Caminho do arquivo salvo, ou None em caso de erro
        """
        if not self.env:
            print("Nenhum ambiente carregado")
            return None
        
        try:
            import tempfile
            import shutil
            
            output_path = os.path.abspath(output_path)
            output_dir = os.path.dirname(output_path)
            output_filename = os.path.basename(output_path)
            os.makedirs(output_dir, exist_ok=True)
            
            # O UnityPy salva em um diretório "output/" no CWD atual.
            # Usamos um diretório temporário para controlar o processo.
            with tempfile.TemporaryDirectory() as tmpdir:
                old_cwd = os.getcwd()
                try:
                    os.chdir(tmpdir)
                    # Salva com compressão LZ4 (ampla compatibilidade)
                    # Assinatura: env.save(pack="none"|"lz4"|"lzma", out_path="diretorio")
                    self.env.save(pack="lz4", out_path=".")
                    
                    # Procura o arquivo gerado
                    saved_files = []
                    for root, dirs, files in os.walk(tmpdir):
                        for f in files:
                            full = os.path.join(root, f)
                            if os.path.isfile(full) and not f.startswith('.'):
                                saved_files.append(full)
                    
                    if saved_files:
                        # Prefere o arquivo que parece ser o bundle (não .resource, etc.)
                        source_file = saved_files[0]
                        shutil.copy2(source_file, output_path)
                        
                        if os.path.exists(output_path):
                            size = os.path.getsize(output_path)
                            print(f"✅ Bundle modificado salvo em: {output_path} ({size/1024:.1f} KB)")
                            return output_path
                finally:
                    os.chdir(old_cwd)
            
            print("❌ Arquivo não foi gerado por env.save()")
            return None
                
        except Exception as e:
            print(f"❌ Erro ao salvar bundle modificado: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def has_modifications(self) -> bool:
        """Verifica se há modificações pendentes no ambiente"""
        if not self.env:
            return False
        try:
            return getattr(self.env, 'modified', False)
        except:
            return False

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """Remove caracteres invalidos de nomes de arquivo"""
        invalid = '<>:"/\\|?*'
        for char in invalid:
            name = name.replace(char, '_')
        name = name.strip().strip('.')
        return name or "unnamed"
    
    def get_summary(self) -> Dict[str, Any]:
        """Retorna resumo do bundle carregado"""
        type_counts = {}
        for a in self.assets:
            t = a.type
            type_counts[t] = type_counts.get(t, 0) + 1
        
        return {
            'file': os.path.basename(self.file_path) if self.file_path else None,
            'total_assets': len(self.assets),
            'type_counts': dict(sorted(type_counts.items(), key=lambda x: -x[1])),
            'types': self.get_all_types()
        }


# ==================== CLI ====================
def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='UABE Python - Extrator de Asset Bundles Unity com UnityPy',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:
  python uabe_py.py info arquivo.unity3d
  python uabe_py.py list arquivo.unity3d
  python uabe_py.py extract arquivo.unity3d -o ./saida
  python uabe_py.py extract arquivo.unity3d -o ./saida -t Texture2D TextAsset
  python uabe_py.py extract-one arquivo.unity3d 12345 -o ./saida
  python uabe_py.py serve --port 5000
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Comandos disponiveis')
    
    # Comando: info
    info_parser = subparsers.add_parser('info', help='Mostra informacoes gerais do bundle')
    info_parser.add_argument('file', help='Arquivo .unity3d/.bundle')
    
    # Comando: list
    list_parser = subparsers.add_parser('list', help='Lista todos os assets')
    list_parser.add_argument('file', help='Arquivo .unity3d/.bundle')
    list_parser.add_argument('-t', '--type', help='Filtrar por tipo (ex: Texture2D)')
    
    # Comando: extract
    extract_parser = subparsers.add_parser('extract', help='Extrai assets')
    extract_parser.add_argument('file', help='Arquivo .unity3d/.bundle')
    extract_parser.add_argument('-o', '--output', default='./exports', help='Diretorio de saida')
    extract_parser.add_argument('-t', '--types', nargs='+', help='Tipos para extrair')
    
    # Comando: extract-one
    one_parser = subparsers.add_parser('extract-one', help='Extrai um asset especifico por Path ID')
    one_parser.add_argument('file', help='Arquivo .unity3d/.bundle')
    one_parser.add_argument('path_id', type=int, help='Path ID do asset')
    one_parser.add_argument('-o', '--output', default='./exports', help='Diretorio de saida')
    
    # Comando: serve (web interface)
    serve_parser = subparsers.add_parser('serve', help='Inicia interface web localhost')
    serve_parser.add_argument('--host', default='127.0.0.1', help='Host (padrao: 127.0.0.1)')
    serve_parser.add_argument('--port', type=int, default=5000, help='Porta (padrao: 5000)')
    
    args = parser.parse_args()
    
    if args.command == 'serve':
        from app import create_app
        app = create_app()
        print(f"🌐 UABE Python rodando em http://{args.host}:{args.port}")
        app.run(host=args.host, port=args.port, debug=False)
        return
    
    if not args.command or not hasattr(args, 'file'):
        parser.print_help()
        return
    
    uabe = UABEPython()
    print(f"Carregando {args.file}...")
    
    if not uabe.load_file(args.file):
        print("Falha ao carregar o arquivo.")
        return
    
    if args.command == 'info':
        summary = uabe.get_summary()
        print(f"\n📦 Arquivo: {summary['file']}")
        print(f"📊 Total de assets: {summary['total_assets']}")
        print(f"\n📋 Tipos de assets encontrados:")
        for t, count in summary['type_counts'].items():
            print(f"  {t}: {count}")
    
    elif args.command == 'list':
        assets = uabe.assets
        if args.type:
            assets = uabe.get_assets_by_type(args.type)
        
        print(f"\n📋 {len(assets)} assets encontrados:\n")
        print(f"{'ID':<12} {'Tipo':<18} {'Nome':<30} {'Tamanho':<10}")
        print("-" * 80)
        for a in assets:
            name = a.name[:28] if a.name else "(sem nome)"
            size = f"{a.size/1024:.1f}KB" if a.size > 0 else "-"
            print(f"{a.path_id:<12} {a.type:<18} {name:<30} {size:<10}")
    
    elif args.command == 'extract':
        print(f"\n📤 Extraindo para {args.output}...")
        results = uabe.extract_all(args.output, args.types)
        total = sum(len(v) for v in results.values())
        print(f"\n✅ Extraidos {total} arquivos:")
        for t, files in results.items():
            print(f"  {t}: {len(files)} arquivos")
    
    elif args.command == 'extract-one':
        print(f"\n📤 Extraindo asset Path ID {args.path_id}...")
        result = uabe.extract_asset(args.path_id, args.output)
        if result:
            print(f"✅ Salvo em: {result}")
        else:
            print("❌ Falha na extracao")


if __name__ == '__main__':
    main()
