from datetime import date, timedelta

from flask import Blueprint, g, render_template

from .. import db
from .estoque import ALERTAS, STATUS

bp = Blueprint("painel", __name__)


@bp.route("/")
def inicio():
    con = db.get_db()
    u = g.usuario
    filtro, params = u.filtro_unidade("e.unidade_id")

    por_status = {s: 0 for s in STATUS}
    for r in con.execute(f"SELECT status, COUNT(*) n FROM equipamentos e WHERE {filtro} "
                         "GROUP BY status", params):
        por_status[r["status"]] = r["n"]
    total = sum(por_status.values())

    por_unidade = con.execute(f"""
        SELECT un.nome,
               COUNT(e.id) total,
               SUM(e.status = 'Em uso') em_uso,
               SUM(e.status = 'Em estoque') estoque,
               SUM(e.status = 'Em manutenção') manutencao
        FROM unidades un
        LEFT JOIN equipamentos e ON e.unidade_id = un.id AND e.status != 'Baixado'
        WHERE un.ativa = 1 AND {u.filtro_unidade('un.id')[0]}
        GROUP BY un.id ORDER BY un.nome""", u.filtro_unidade("un.id")[1]).fetchall()

    por_tipo = con.execute(f"""
        SELECT tipo, COUNT(*) n FROM equipamentos e
        WHERE status != 'Baixado' AND {filtro}
        GROUP BY tipo ORDER BY n DESC LIMIT 8""", params).fetchall()

    hoje = date.today()
    garantias = con.execute(f"""
        SELECT e.id, e.tipo, e.marca, e.modelo, e.patrimonio, e.garantia_ate, un.nome unidade
        FROM equipamentos e JOIN unidades un ON un.id = e.unidade_id
        WHERE e.status != 'Baixado' AND e.garantia_ate BETWEEN ? AND ? AND {filtro}
        ORDER BY e.garantia_ate LIMIT 8""",
        [hoje.isoformat(), (hoje + timedelta(days=60)).isoformat()] + params).fetchall()

    senhas_antigas = []
    if u.pode_cofre:
        f2, p2 = u.filtro_unidade("c.unidade_id", incluir_geral=True)
        limite = (hoje - timedelta(days=180)).isoformat()
        senhas_antigas = con.execute(f"""
            SELECT c.id, c.sistema, c.senha_alterada_em, un.nome unidade
            FROM cofre c LEFT JOIN unidades un ON un.id = c.unidade_id
            WHERE c.senha_alterada_em < ? AND {f2}
            ORDER BY c.senha_alterada_em LIMIT 8""", [limite] + p2).fetchall()

    atencao = []
    for chave, (rotulo, cond) in ALERTAS.items():
        n = con.execute(f"SELECT COUNT(*) FROM equipamentos e LEFT JOIN hardware h ON h.equipamento_id = e.id "
                        f"WHERE e.status != 'Baixado' AND {cond} AND {filtro}", params).fetchone()[0]
        atencao.append({"chave": chave, "rotulo": rotulo, "n": n})
    com_hw = con.execute(f"SELECT COUNT(*) FROM equipamentos e JOIN hardware h ON h.equipamento_id = e.id "
                         f"WHERE e.status != 'Baixado' AND {filtro}", params).fetchone()[0]

    return render_template("painel.html", atencao=atencao, com_hw=com_hw, por_status=por_status, total=total,
                           por_unidade=por_unidade, por_tipo=por_tipo,
                           garantias=garantias, senhas_antigas=senhas_antigas)
