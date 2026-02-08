#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Servidor Flask para Gestão de Condomínio
Lê dados de ficheiros DBF e serve páginas HTML dinâmicas
"""

import os
import sys
import traceback
from pathlib import Path
from dbfread import DBF
from datetime import datetime
from flask import Flask, render_template, jsonify

app = Flask(__name__)

# ====================================================================
# CONFIGURAÇÕES GLOBAIS
# ====================================================================

def get_base_dir():
    """
    Retorna o diretório base correto tanto para desenvolvimento quanto para executável.
    
    Quando rodando como executável PyInstaller:
    - sys.executable aponta para dist/GestaoCondominio/GestaoCondominio.exe
    - Precisamos do diretório pai (dist/) onde estão as pastas de dados
    
    Quando rodando como script Python:
    - __file__ aponta para o arquivo .py
    - O diretório do arquivo é o diretório base
    """
    if getattr(sys, 'frozen', False):
        # Rodando como executável PyInstaller
        # sys.executable = dist/GestaoCondominio/GestaoCondominio.exe
        # Queremos dist/ (o pai do pai)
        return Path(sys.executable).parent.parent
    else:
        # Rodando como script Python
        return Path(__file__).resolve().parent

# Paths
BASE_DIR = get_base_dir()
PASTA_CORRENTE = BASE_DIR / "corrente"
PASTA_HISTORICO = BASE_DIR / "historico"
# Database
DBF_CODEPAGE = 'cp1252'

app.template_folder = 'templates'

def ler_dbf(nome_ficheiro):
    """Lê um ficheiro DBF e retorna lista de dicionários"""
    caminho = os.path.join(PASTA_CORRENTE, nome_ficheiro)
    try:
        tabela = DBF(caminho, encoding='latin-1', lowernames=True)
        return list(tabela)
    except Exception as e:
        print(f"Erro ao ler {nome_ficheiro}: {e}")
        return []

@app.route('/')
def index():
    """Página principal"""
    # Calcular resumo financeiro a partir do Balanco.dbf
    try:
        balanco_dbf = ler_dbf('Balanco.dbf')
        
        total_receitas = 0.0
        total_despesas = 0.0
        saldo_anterior = 0.0
        saldo_final = 0.0
        
        for linha in balanco_dbf:
            conta = linha.get('conta', '').strip().upper()
            tipo = linha.get('tipo', '').strip().upper()
            valor = float(linha.get('valor', 0) or 0)
            
            # Busca para saldo anterior - linha com TSA ou "Total saldo anterior"
            # Também verifica SUBTOTAL + TSA
            if 'TSA' in conta:
                saldo_anterior = valor
            elif tipo == 'SUBTOTAL' and 'SALDO' in conta and 'ANTERIOR' in conta:
                saldo_anterior = valor
            elif 'TOTAL' in conta and 'SALDO' in conta and 'ANTERIOR' in conta:
                saldo_anterior = valor
            # Total receitas
            elif tipo == 'SUBTOTAL' and 'RECEITAS' in conta:
                total_receitas = valor
            elif 'TOTAL' in conta and 'RECEITAS' in conta:
                total_receitas = valor
            # Total despesas  
            elif tipo == 'SUBTOTAL' and 'DESPESAS' in conta:
                total_despesas = valor
            elif 'TOTAL' in conta and 'DESPESAS' in conta:
                total_despesas = valor
            # Saldo final
            elif tipo == 'SALDO' and 'FINAL' in conta:
                saldo_final = valor
            elif tipo == 'TOTAL' and conta == 'TOTAL':
                # Pode ser o saldo final na última linha
                if saldo_final == 0.0:
                    saldo_final = valor
        
        # Se não encontrou saldo final, calcular
        if saldo_final == 0.0:
            saldo_final = saldo_anterior + total_receitas - total_despesas
        
        resumo = {
            'total_receitas': f"{total_receitas:.2f}",
            'total_despesas': f"{total_despesas:.2f}",
            'saldo_anterior': f"{saldo_anterior:.2f}",
            'saldo_final': f"{saldo_final:.2f}"
        }
    except Exception as e:
        print(f"Erro ao calcular resumo: {e}")
        import traceback
        traceback.print_exc()
        resumo = {
            'total_receitas': "0.00",
            'total_despesas': "0.00",
            'saldo_anterior': "0.00",
            'saldo_final': "0.00"
        }
    
    return render_template('index.html', resumo=resumo)

@app.route('/bancos')
def bancos():
    """Página de movimentos bancários"""
    try:
        dados = ler_dbf('Bancos.dbf')
        
        print(f"=== DEBUG BANCOS ===")
        print(f"Total de registos: {len(dados)}")
        
        # Debug: mostrar campos disponíveis
        if dados and len(dados) > 0:
            print(f"Campos disponíveis em Bancos.dbf: {list(dados[0].keys())}")
            print(f"Primeiro registo: {dados[0]}")
        
        return render_template('bancos.html', dados=dados)
    
    except FileNotFoundError:
        print("ERRO: Ficheiro Bancos.dbf não encontrado!")
        return render_template('bancos.html', dados=[])
    except Exception as e:
        print(f"Erro ao ler movimentos: {e}")
        import traceback
        traceback.print_exc()
        return render_template('bancos.html', dados=[])

@app.route('/dashboard')
def dashboard():
    """Dashboard com gráficos"""
    try:
        receitas_n = ler_dbf('ReceitasN.dbf')
        receitas_e = ler_dbf('ReceitasE.dbf')
        despesas = ler_dbf('Despesas.dbf')
        balanco_dbf = ler_dbf('Balanco.dbf')
        
        # Preparar dados para os gráficos
        meses = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 
                'jul', 'ago', 'set', 'out', 'nov', 'dez']
        
        # Receitas Normais por fração (excluir linha TOTAIS)
        rec_n_fracoes = {}
        for linha in receitas_n:
            fracao = linha.get('fraccao', '').strip()
            if fracao and fracao.upper() != 'TOTAIS':
                rec_n_fracoes[fracao] = [float(linha.get(mes, 0) or 0) for mes in meses]
        
        # Receitas Extraordinárias por fração (excluir linha TOTAIS)
        rec_e_fracoes = {}
        for linha in receitas_e:
            fracao = linha.get('fraccao', '').strip()
            if fracao and fracao.upper() != 'TOTAIS':
                rec_e_fracoes[fracao] = [float(linha.get(mes, 0) or 0) for mes in meses]
        
        # Despesas mensais - pegar da linha TOTAIS
        despesas_mensais = []
        for linha in despesas:
            if linha.get('despesas', '').strip().upper() == 'TOTAIS':
                despesas_mensais = [float(linha.get(mes, 0) or 0) for mes in meses]
                break
        
        if not despesas_mensais:
            despesas_mensais = [0] * 12
        
        # Composição do balanço - ler do Balanco.dbf
        total_receitas = 0.0
        total_despesas = 0.0
        saldo_anterior = 0.0
        saldo_final = 0.0
        
        for linha in balanco_dbf:
            conta = linha.get('conta', '').strip().upper()
            tipo = linha.get('tipo', '').strip().upper()
            valor = float(linha.get('valor', 0) or 0)
            
            if 'TSA' in conta:
                saldo_anterior = valor
            elif tipo == 'SUBTOTAL' and 'SALDO' in conta and 'ANTERIOR' in conta:
                saldo_anterior = valor
            elif tipo == 'SUBTOTAL' and 'RECEITAS' in conta:
                total_receitas = valor
            elif tipo == 'SUBTOTAL' and 'DESPESAS' in conta:
                total_despesas = valor
            elif tipo == 'SALDO' and 'FINAL' in conta:
                saldo_final = valor
            elif tipo == 'TOTAL' and conta == 'TOTAL':
                if saldo_final == 0.0:
                    saldo_final = valor
        
        # Se não encontrou saldo final, calcular
        if saldo_final == 0.0:
            saldo_final = saldo_anterior + total_receitas - total_despesas
        
        balanco_data = {
            'saldo_anterior': saldo_anterior,
            'total_receitas': total_receitas,
            'total_despesas': total_despesas,
            'saldo_corrente': total_receitas - total_despesas,
            'saldo_final': saldo_final
        }
        
        return render_template('dashboard.html',
                             rec_n_fracoes=rec_n_fracoes,
                             rec_e_fracoes=rec_e_fracoes,
                             despesas_mensais=despesas_mensais,
                             balanco=balanco_data)
    
    except Exception as e:
        print(f"Erro no dashboard: {e}")
        import traceback
        traceback.print_exc()
        return render_template('dashboard.html',
                             rec_n_fracoes={},
                             rec_e_fracoes={},
                             despesas_mensais=[],
                             balanco={})

@app.route('/receitas-normais')
def receitas_normais():
    """Página de receitas normais"""
    dados = ler_dbf('ReceitasN.dbf')
    
    # Não calcular totais - já vêm do DBF
    # Apenas processar os dados para mostrar
    for linha in dados:
        # Garantir que campos vazios aparecem como vazio, não como 0
        for campo in linha.keys():
            if linha[campo] is None or linha[campo] == 0:
                linha[campo] = None
    
    return render_template('receitasN.html', dados=dados)

@app.route('/receitas-extraordinarias')
def receitas_extraordinarias():
    """Página de receitas extraordinárias"""
    dados = ler_dbf('ReceitasE.dbf')
    
    # Não calcular totais - já vêm do DBF
    # Apenas processar os dados para mostrar
    for linha in dados:
        # Garantir que campos vazios aparecem como vazio, não como 0
        for campo in linha.keys():
            if linha[campo] is None or linha[campo] == 0:
                linha[campo] = None
    
    return render_template('receitasE.html', dados=dados)

@app.route('/despesas')
def despesas():
    """Página de despesas"""
    dados = ler_dbf('Despesas.dbf')
    
    # Não calcular totais - já vêm do DBF
    # Apenas processar os dados para mostrar
    for linha in dados:
        # Garantir que campos vazios aparecem como vazio, não como 0
        for campo in linha.keys():
            if linha[campo] is None or linha[campo] == 0:
                linha[campo] = None
    
    return render_template('despesas.html', dados=dados)

@app.route('/balanco')
def balanco():
    """Página de balanço - lê dados dos DBF dinamicamente"""
    # Ler dados do Balanco.dbf
    balanco_dbf = ler_dbf('Balanco.dbf')
    
    despesas_lista = []
    total_despesas = 0.0
    total_receitas = 0.0
    quotas_normais = 0.0
    quotas_extras = 0.0
    juros = 0.0
    saldo_anterior_total = 0.0
    deposito_ordem = 0.0
    numerario_caixa = 0.0
    saldo_final = 0.0
    
    for linha in balanco_dbf:
        conta = linha.get('conta', '').strip().upper()
        tipo = linha.get('tipo', '').strip().upper()
        valor = float(linha.get('valor', 0) or 0)
        
        # Despesas individuais
        if tipo == 'DESPESA':
            despesas_lista.append({
                'nome': linha.get('conta', '').strip(),
                'valor': valor
            })
        # Saldo anterior
        elif 'TSA' in conta:
            saldo_anterior_total = valor
        elif tipo == 'SUBTOTAL' and 'SALDO' in conta and 'ANTERIOR' in conta:
            saldo_anterior_total = valor
        elif 'DEPÓSITO ORDEM' in conta or 'DEPOSITO ORDEM' in conta:
            deposito_ordem = valor
        elif 'NUMERÁRIO CAIXA' in conta or 'NUMERARIO CAIXA' in conta:
            numerario_caixa = valor
        # Totais
        elif tipo == 'SUBTOTAL' and 'DESPESAS' in conta:
            total_despesas = valor
        elif 'QUOTAS NORMAIS' in conta:
            quotas_normais = valor
        elif 'QUOTAS EXTRAS' in conta:
            quotas_extras = valor
        elif 'JUROS' in conta and tipo == 'RECEITA':
            juros = valor
        elif tipo == 'SUBTOTAL' and 'RECEITAS' in conta:
            total_receitas = valor
        elif tipo == 'SALDO' and 'FINAL' in conta:
            saldo_final = valor
    
    # Saldo anterior do Balanco.dbf
    saldo_anterior = {
        'deposito_poupanca': 0.0,
        'deposito_ordem': deposito_ordem,
        'numerario_caixa': numerario_caixa,
        'total': saldo_anterior_total
    }
    
    # Receitas detalhadas
    receitas_detalhes = {
        'quotas_normais': quotas_normais,
        'quotas_extras': quotas_extras,
        'juros': juros,
        'total': total_receitas
    }
    
    # Cálculos finais
    total_creditos = saldo_anterior['total'] + receitas_detalhes['total']
    if saldo_final == 0.0:
        saldo_final = total_creditos - total_despesas
    total_debitos = total_despesas + saldo_final
    
    return render_template('balanco.html',
                         despesas=despesas_lista,
                         total_despesas=total_despesas,
                         saldo_anterior=saldo_anterior,
                         receitas=receitas_detalhes,
                         saldo_final=saldo_final,
                         total_debitos=total_debitos,
                         total_creditos=total_creditos)

# API endpoints para dados JSON (útil para JavaScript)
@app.route('/api/receitas-normais')
def api_receitas_normais():
    """API: Retorna receitas normais em JSON"""
    dados = ler_dbf('ReceitasN.dbf')
    return jsonify(dados)

@app.route('/api/receitas-extraordinarias')
def api_receitas_extraordinarias():
    """API: Retorna receitas extraordinárias em JSON"""
    dados = ler_dbf('ReceitasE.dbf')
    return jsonify(dados)

@app.route('/api/despesas')
def api_despesas():
    """API: Retorna despesas em JSON"""
    dados = ler_dbf('Despesas.dbf')
    return jsonify(dados)

@app.route('/api/balanco')
def api_balanco():
    """API: Retorna balanço em JSON"""
    dados = ler_dbf('Balanco.dbf')
    return jsonify(dados)

@app.route('/api/movimentos')
def api_movimentos():
    """API: Retorna movimentos bancários em JSON"""
    dados = ler_dbf('Bancos.dbf')
    return jsonify(dados)

@app.route('/api/test-movimentos')
def api_test_movimentos():
    """API de teste: Verifica se Bancos.dbf existe e mostra estrutura"""
    try:
        import os
        caminho = os.path.join(PASTA_CORRENTE, 'Bancos.dbf')
        
        if not os.path.exists(caminho):
            return jsonify({
                'erro': 'Ficheiro não encontrado',
                'caminho': caminho,
                'existe': False
            })
        
        dados = ler_dbf('Bancos.dbf')
        
        resultado = {
            'existe': True,
            'caminho': caminho,
            'total_registos': len(dados),
            'campos': list(dados[0].keys()) if dados else [],
            'primeiros_3_registos': dados[:3] if len(dados) >= 3 else dados
        }
        
        return jsonify(resultado)
    except Exception as e:
        return jsonify({
            'erro': str(e),
            'traceback': traceback.format_exc()
        })

if __name__ == '__main__':
    # Verificar se as pastas existem
    if not os.path.exists(PASTA_CORRENTE):
        print(f"AVISO: Pasta '{PASTA_CORRENTE}' não encontrada!")
        print("Crie a pasta e coloque os ficheiros DBF lá.")
    
    if not os.path.exists(app.template_folder):
        print(f"AVISO: Pasta '{app.template_folder}' não encontrada!")
        print("Crie a pasta e coloque os templates HTML lá.")
    
    print("=" * 50)
    print("🏢 Servidor Flask - Gestão de Condomínio")
    print("=" * 50)
    print("📁 Pasta DBF:", PASTA_CORRENTE)
    print("📄 Templates:", app.template_folder)
    print("🌐 Servidor: http://localhost:8800")
    print("=" * 50)
    
    app.run(debug=True, host='0.0.0.0', port=8800)