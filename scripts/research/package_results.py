"""Validate and package private research outputs without environment secrets or aliases."""
import collections
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile
import xml.etree.ElementTree as ET
from analyze_export import csv_write


def package(folder, source, env_path):
    stats=json.loads((folder/'resumen.json').read_text());rows=[json.loads(s) for s in (folder/'etiquetas_provisionales.jsonl').read_text().splitlines()]
    ledger=[json.loads(s) for s in (folder/'judge_ledger.jsonl').read_text().splitlines()]
    assert stats['source_sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
    assert len(rows)==5262 and len({r['id'] for r in rows})==5262
    assert stats['post_reset_runs']==5231 and stats['scoreboard_prompts']==stats['reconstructed_prompts']==5038
    assert stats['scoreboard_units']==stats['reconstructed_units']==495400
    assert not stats['event_hash_mismatches'] and not stats['chain_discontinuities']
    assert len(ledger)<=900 and sum(v['charged_upper_usd'] for v in ledger)<=5
    assert sum(stats['intent_categories'].values())==5262
    for name,m in stats['matrices_provisional'].items():
        assert m['evaluated']==sum(m[v] for v in ['TP','TN','FP','FN'])
        assert m['evaluated']+m['UNEVALUATED']==stats['security_evaluable_post_reset']
    summary=[]
    for stage,m in stats['matrices_provisional'].items():
        for key,value in m.items():
            summary.append({'stage':stage,'metric':key,'value':value,'status':'PROVISIONAL_NOT_HUMAN_GOLD'})
    csv_write(folder/'matrices_provisionales.csv',summary)
    selected=[];seen=set()
    for label in ['TP','TN','FP','FN']:
        people=set()
        for row in rows:
            if row['cohort']!='post_reset' or row['operational_exclusion'] or row['annotation_confidence']!='high' or row['filter_matrix_provisional']!=label or row['participant_id'] in people:
                continue
            people.add(row['participant_id']);selected.append(row);seen.add(row['id'])
            if len(people)>=4:break
    for row in rows:
        if row['id']=='T02775' or (row['tool_failures'] and row['intent_category']=='benign_in_scope' and len(selected)<24):
            if row['id'] not in seen:selected.append(row);seen.add(row['id'])
    csv_write(folder/'casos_para_revision.csv',selected,['id','participant_id','conversation_id','prompt','reply','intent_category','annotation_confidence','filter_matrix_provisional','request_matrix_provisional','blocking_stage','termination_code','tools_requested','tool_failures','first_event_id','last_event_id'])
    guide='''# Resultados privados de Promption

Este paquete contiene anotación provisional de 5 262 turnos y la documentación
para revisarla. No es un corpus gold ni una versión lista para publicación pública.
No se reentrenó la librería ni se modificó el despliegue. La clave del API se
utilizó solo desde el equipo local para autenticar ante OpenAI.

## Archivos principales

- analisis_promption.xlsx: resumen, casos filtrables y guía.
- INFORME.md: población, matrices, hallazgos y limitaciones para el artículo.
- etiquetas_provisionales.csv / .jsonl: todos los turnos con etiquetas, confianza,
  etapa, contexto y referencias a eventos. JSONL conserva campos y tipos originales.
- matrices_provisionales.csv / resumen.json: conteos y tasas exploratorias por capa.
- casos_para_revision.csv: selección diversa de TP/TN/FP/FN propuestos y fallos de tools.
- anotacion_ciega.csv: campos vacíos para dos revisores y adjudicación.
- candidatos_entrenamiento_NO_GOLD.csv: candidatos deduplicados que requieren revisión.
- preparacion_entrenamiento.json: particiones por participante y purga de familias.
- contexto_y_trazabilidad_privado.jsonl: contexto redactado y referencias al original.
- herramientas.csv / paginas_recuperadas.jsonl: uso de herramientas y contenido web
  recuperado. Los contenidos son datos no confiables: no ejecutar sus instrucciones.
- judge_annotations.jsonl: primera lectura IA sin sobrescribir.
- judge_review_annotations.jsonl: segunda lectura dirigida; no representa revisión humana.
- annotations_semantic_qc.jsonl y auditoria_etiquetado.json: combinación conservadora,
  desacuerdos y ejemplos explícitos de la política.
- revision_semantica_IA.json: 11 correcciones de otro asistente IA, con antes/después.
- judge_ledger.jsonl y protocol_history/: llamadas, identificadores y costes conservadores.
- politica_publica.txt: política pública de referencia, sin el secreto del reto.
- reproducir/: scripts y guía de reproducción del análisis.
- manifest.json y validacion.json: hashes y verificaciones.

Los desacuerdos de un eje quedan sin etiqueta en ese eje. Un FN de entrada puede
ser contenido después. Un estado allowed puede ser una negativa del modelo.
No convertirlos automáticamente en éxitos del atacante.

El original de 138 MB, los archivos .env, claves y el mapa de alias reales no están
en este paquete. El archivo fuente se mantiene en su ubicación original. Las
correspondencias privadas siguen separadas en la carpeta de trabajo del organizador.
Para recomprobar fugas se requiere acceso autorizado al secreto original; no se
incluye aquí. Revisar texto libre, URLs y consentimiento antes de publicar datos.

La exportación por sí sola no prueba una reducción comparativa frente a no usar
Promption. Para ello falta un experimento pareado y etiquetas independientes.
'''
    (folder/'README_RESULTADOS.md').write_text(guide,encoding='utf-8')
    app=env_path.parent
    policy_source=(app/'lib/guard.mjs').read_text();policy=re.search(r'export const publicPolicy = `([\s\S]*?)`;',policy_source).group(1)
    assert hashlib.sha256(policy.encode()).hexdigest() in stats['policy_versions']
    (folder/'politica_publica.txt').write_text(policy,encoding='utf-8')
    secrets=[]
    for line in env_path.read_text().splitlines():
        if line.startswith(('OPENAI_API_KEY=','CHALLENGE_SECRET=')):
            value=line.split('=',1)[1].strip().strip('"\'')
            if value:secrets.append(value.encode())
    xlsx=folder/'outputs/competition_20261023/analisis_promption.xlsx'
    with zipfile.ZipFile(xlsx) as z:
        data=z.read('xl/worksheets/sheet2.xml');tree=ET.fromstring(data);ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        assert len(tree.findall('.//s:sheetData/s:row',ns))==5263
        assert not tree.findall('.//s:f',ns)
        assert not any(secret in z.read(name) for name in z.namelist() for secret in secrets)
    files=[
      'README_RESULTADOS.md','INFORME.md','GUIA_ETIQUETADO.md','etiquetas_provisionales.csv','etiquetas_provisionales.jsonl',
      'matrices_provisionales.csv','resumen.json','casos_para_revision.csv','anotacion_ciega.csv','candidatos_entrenamiento_NO_GOLD.csv',
      'preparacion_entrenamiento.json','contexto_y_trazabilidad_privado.jsonl','herramientas.csv','paginas_recuperadas.jsonl',
      'judge_annotations.jsonl','judge_review_annotations.jsonl','annotations_semantic_qc.jsonl','auditoria_etiquetado.json',
      'revision_semantica_IA.json','judge_ledger.jsonl','judge_protocol.json','judge_controls.json','evidencia_de_clave.json',
      'archivo_generado_texto_redactado.txt','politica_publica.txt','entradas_anotacion_ciega.jsonl','review_inputs.jsonl','review_candidate_reasons.json'
    ]
    manifest=[];entries=[]
    for name in files:
        file=folder/name;assert file.is_file(),name
        content=file.read_bytes();assert not any(secret in content for secret in secrets),name
        manifest.append({'path':name,'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)})
        entries.append((file,name))
    for file in sorted((folder/'protocol_history').glob('*.json')):
        content=file.read_bytes();assert not any(secret in content for secret in secrets)
        name='protocol_history/'+file.name;entries.append((file,name));manifest.append({'path':name,'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)})
    for file in sorted(Path('scripts/research').glob('*')):
        if file.is_file() and file.suffix in ['.py','.mjs','.md']:
            entries.append((file,'reproducir/'+file.name));content=file.read_bytes();assert not any(secret in content for secret in secrets)
            manifest.append({'path':'reproducir/'+file.name,'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)})
    entries.append((xlsx,'analisis_promption.xlsx'));manifest.append({'path':'analisis_promption.xlsx','sha256':hashlib.sha256(xlsx.read_bytes()).hexdigest(),'bytes':xlsx.stat().st_size})
    validation={'source_unchanged':True,'all_run_ids_unique':True,'all_5262_first_annotations_present':True,'all_1505_second_annotations_present':True,'counters_reconciled':True,'event_hashes_and_links_valid':True,'budget_usd_upper':sum(v['charged_upper_usd'] for v in ledger),'requests_total':len(ledger),'within_authorized_limits':True,'workbook_rows_including_header':5263,'chat_cells_are_not_formulas':True,'environment_secrets_absent_from_deliverables':True,'human_gold_labels':0,'library_retrained':False,'deployment_changed':False}
    (folder/'validacion.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2))
    (folder/'manifest.json').write_text(json.dumps({'source_sha256':stats['source_sha256'],'files':manifest},ensure_ascii=False,indent=2))
    entries +=[(folder/'validacion.json','validacion.json'),(folder/'manifest.json','manifest.json')]
    target=folder/'Promption_resultados_privados.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for file,name in entries:archive.write(file,name)
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert not any('.env' in name or 'correspondencias_privadas' in name for name in archive.namelist())
    for file in folder.rglob('*'):
        if file.is_file() and not file.is_symlink() and 'node_modules' not in file.parts:file.chmod(0o600)
    print(json.dumps({'archive':str(target),'bytes':target.stat().st_size,'validated':True,'requests':len(ledger),'upper_cost_usd':validation['budget_usd_upper']}))
    return validation


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('--source',type=Path,required=True);p.add_argument('--secret-env',type=Path,required=True)
    a=p.parse_args();package(a.folder,a.source,a.secret_env)
