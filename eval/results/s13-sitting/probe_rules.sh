#!/usr/bin/env bash
# S13-R1 sitting: decision 1's rules on the gate's 4 traced KEPs (2572 + held-out 2579, 2799, 4858).
# Free: GitHub API reads (needs `gh auth login`) and the dev database (`make up`).
# Prints only field lines, ids, dates and distances (no GitHub prose beyond the field lines).
# Usage: bash eval/results/s13-sitting/probe_rules.sh > eval/results/s13-sitting/probe_rules.log
set -euo pipefail
psql() { docker compose exec -T db psql -U orgknow -d orgknow -At "$@"; }

echo "== 1. Tracking-issue template fields (Enhancement Proposal, Discussion Link, KEP update PRs)"
for n in 2572 2579 2799 4858 1498; do
  gh api "repos/kubernetes/enhancements/issues/$n" -q '"#\(.number) \(.title) | state \(.state)"'
  gh api "repos/kubernetes/enhancements/issues/$n" -q .body \
    | grep -i -E "Enhancement Proposal:|Discussion Link:|KEP \(.k/enhancements.\) update PR" | head -3 || true
done

echo; echo "== 2. Stored texts linking each KEP (blog, release record, docs, governance), earliest first"
psql -c "
select k.kep, d.canonical_id, d.source_type, min(v.valid_from_date)::date first_seen
from (values ('2572','2572-release-cadence'),('2579','2579-psp-replacement'),
             ('2799','2799-reduction-of-secret-based-service-account-token'),('4858','4858-ip-cidr-validation')) k(kep, dir)
join chunks c on c.text ~* ('(' || k.dir || '|enhancements/issues/' || k.kep || '([^0-9]|\$)|KEP-' || k.kep || '([^0-9]|\$))')
join document_versions v on v.id=c.document_version_id join documents d on d.id=v.document_id
where d.canonical_id <> 'kep:'||k.kep and d.source_type in ('blog_post','release_record','docs_page','governance_doc')
group by 1,2,3 order by 1,4"

echo; echo "== 3. Current docs: nearest texts valid at 1.37 to each KEP's first Summary chunk vector"
psql -c "
with q as (
  select d.canonical_id kep, e.embedding from documents d join document_versions v on v.document_id=d.id
  join chunks c on c.document_version_id=v.id join embeddings e on e.content_hash=c.content_hash
  where d.canonical_id in ('kep:2572','kep:2579','kep:2799','kep:4858') and v.valid_until_date is null and c.heading_path[2]='Summary'
    and c.ordinal=(select min(c2.ordinal) from chunks c2 where c2.document_version_id=v.id and c2.heading_path[2]='Summary')
), cand as (
  select distinct on (q.kep, c.content_hash) q.kep, d.canonical_id, c.heading_path, c.content_hash, (e.embedding <=> q.embedding) dist
  from q, documents d join document_versions v on v.document_id=d.id join chunks c on c.document_version_id=v.id
  join embeddings e on e.content_hash=c.content_hash
  where d.source_type in ('docs_page','release_record','governance_doc','feature_gate_reference') and d.canonical_id not like 'changelog:%'
    and v.valid_from_release<=37 and coalesce(v.valid_until_release,37)>=37
)
select kep, rank, canonical_id, array_to_string(heading_path,' > '), round(dist::numeric,3) from (
  select *, row_number() over (partition by kep order by dist, content_hash) rank from cand) x
where rank<=3 order by kep, rank"
