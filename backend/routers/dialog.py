"""
Endpoints para abrir diálogos nativos de seleção de arquivo/pasta no Windows.
Usa PowerShell + System.Windows.Forms internamente.
Em Linux retorna path vazio (sem erro).
"""

import subprocess
import sys
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/dialog", tags=["dialog"])


class PickResult(BaseModel):
    path: str


def _run_ps(script: str) -> str:
    if sys.platform != "win32":
        return ""
    result = subprocess.run(
        ["powershell", "-STA", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=120,
    )
    return result.stdout.strip()


@router.get("/folder", response_model=PickResult)
def pick_folder(initial: str = "C:\\"):
    """Abre FolderBrowserDialog e retorna o caminho selecionado."""
    initial_safe = initial.replace("'", "''")
    path = _run_ps(f"""
Add-Type -AssemblyName System.Windows.Forms
$d = New-Object System.Windows.Forms.FolderBrowserDialog
$d.Description = 'Selecione a pasta de destino dos backups'
$d.ShowNewFolderButton = $true
$d.SelectedPath = '{initial_safe}'
$d.RootFolder = [System.Environment+SpecialFolder]::MyComputer
if ($d.ShowDialog() -eq 'OK') {{ Write-Output $d.SelectedPath }}
""")
    return PickResult(path=path)


@router.get("/file", response_model=PickResult)
def pick_file(filter: str = "Todos os arquivos|*.*", initial: str = "C:\\"):
    """Abre OpenFileDialog e retorna o caminho selecionado."""
    initial_safe = initial.replace("'", "''")
    filter_safe  = filter.replace("'", "''")
    path = _run_ps(f"""
Add-Type -AssemblyName System.Windows.Forms
$d = New-Object System.Windows.Forms.OpenFileDialog
$d.Filter = '{filter_safe}'
$d.InitialDirectory = '{initial_safe}'
$d.CheckFileExists = $true
if ($d.ShowDialog() -eq 'OK') {{ Write-Output $d.FileName }}
""")
    return PickResult(path=path)
