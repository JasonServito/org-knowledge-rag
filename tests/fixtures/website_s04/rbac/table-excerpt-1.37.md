<table>
<colgroup><col style="width: 25%;" /><col style="width: 25%;" /><col /></colgroup>
<thead>
<tr>
<th>Default ClusterRole</th>
<th>Default ClusterRoleBinding</th>
<th>Description</th>
</tr>
</thead>
<tbody>
<tr>
<td><b>cluster-admin</b></td>
<td><b>system:masters</b> group</td>
<td>Allows super-user access to perform any action on any resource.
When used in a <b>ClusterRoleBinding</b>, it gives full control over every resource in the cluster and in all namespaces.
When used in a <b>RoleBinding</b>, it gives full control over every resource in the role binding's namespace, including the namespace itself.</td>
</tr>
<tr>
<td><b>admin</b></td>
<td>None</td>
<td>Allows admin access, intended to be granted within a namespace using a <b>RoleBinding</b>.

If used in a <b>RoleBinding</b>, allows read/write access to most resources in a namespace,
including the ability to create roles and role bindings within the namespace.
This role does not allow write access to resource quota or to the namespace itself.
This role also does not allow write access to EndpointSlices in clusters created
using Kubernetes v1.22+. More information is available in the
["Write Access for EndpointSlices" section](#write-access-for-endpoints).</td>
</tr>
<tr>
<td><b>edit</b></td>
<td>None</td>
<td>Allows read/write access to most objects in a namespace.

This role does not allow viewing or modifying roles or role bindings.
However, this role allows accessing Secrets and running Pods as any ServiceAccount in
the namespace, so it can be used to gain the API access levels of any ServiceAccount in
the namespace. This role also does not allow write access to EndpointSlices in
clusters created using Kubernetes v1.22+. More information is available in the
["Write Access for EndpointSlices" section](#write-access-for-endpoints).</td>
</tr>
<tr>
<td><b>view</b></td>
<td>None</td>
<td>Allows read-only access to see most objects in a namespace.
It does not allow viewing roles or role bindings.

This role does not allow viewing Secrets, since reading
the contents of Secrets enables access to ServiceAccount credentials
in the namespace, which would allow API access as any ServiceAccount
in the namespace (a form of privilege escalation).</td>
</tr>
</tbody>
</table>
