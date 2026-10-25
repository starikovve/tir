# VXLAN-EVPN Leaf-Spine Fabric — B4Com / OcNOS

Minimal working config: two spines (route reflectors) + two leaf VTEPs,
underlay OSPF, EVPN Type-2/3/4, ingress-replication BUM, symmetric IRB
with anycast gateway, all-active multihoming on leaf-1.

Tested syntax: OcNOS 7.0.x (OcNOS-DC / OcNOS-SP-PLUS). B4Com BCOM OS
is OcNOS-based, CLI is transactional — nothing applies without `commit`.

Topology
--------
```
        lo0: 10.255.0.1/32              lo0: 10.255.0.2/32
  spine-1 10.0.0.0/30 xe1  xe2 10.0.0.4/30  spine-2
       |                      |
  xe3 10.0.0.8/30        xe3 10.0.0.12/30
  leaf-1 (VTEP .11)      leaf-2 (VTEP .12)
  lo0: 10.255.0.11/32    lo0: 10.255.0.12/32
  port-channel po10 -> server (multihomed, ESI)
  irb10100: 192.0.2.1/24 anycast gw in vrf TENANT
```

Numbers are lab values — replace AS, RD/RT, IPs, VNIs with yours.
RD/RT scheme: L2VNI = 10000 + vlan, L3VNI = 20000 + vrf-index.

## spine-1 (spine-2 is symmetric, only lo0 IP and hostname differ)

```
!
hostname spine-1
!
interface loopback0
 ip address 10.255.0.1/32
!
interface xe1
 description to-leaf-1
 ip address 10.0.0.1/30
 ip ospf 1 area 0.0.0.0
!
interface xe2
 description to-leaf-2
 ip address 10.0.0.5/30
 ip ospf 1 area 0.0.0.0
!
router ospf 1
 router-id 10.255.0.1
 network 10.0.0.0 0.0.0.3 area 0.0.0.0
 network 10.0.0.4 0.0.0.3 area 0.0.0.0
 network 10.255.0.1 0.0.0.0 area 0.0.0.0
!
router bgp 65000
 bgp router-id 10.255.0.1
 bgp log-neighbor-changes
 neighbor 10.255.0.11 remote-as 65000
 neighbor 10.255.0.11 update-source loopback0
 neighbor 10.255.0.11 route-reflector-client
 neighbor 10.255.0.12 remote-as 65000
 neighbor 10.255.0.12 update-source loopback0
 neighbor 10.255.0.12 route-reflector-client
 address-family l2vpn evpn
  neighbor 10.255.0.11 activate
  neighbor 10.255.0.12 activate
 exit-address-family
!
end
commit
```

## leaf-1

```
!
hostname leaf-1
!
! --- underlay ---
interface loopback0
 ip address 10.255.0.11/32
!
interface xe3
 description to-spine-1
 ip address 10.0.0.2/30
 ip ospf 1 area 0.0.0.0
!
interface xe4
 description to-spine-2
 ip address 10.0.0.10/30
 ip ospf 1 area 0.0.0.0
!
router ospf 1
 router-id 10.255.0.11
 network 10.0.0.0 0.0.0.3 area 0.0.0.0
 network 10.0.0.8 0.0.0.3 area 0.0.0.0
 network 10.255.0.11 0.0.0.0 area 0.0.0.0
!
! --- VXLAN global (must be committed together) ---
hardware-profile filter vxlan enable
nvo vxlan enable
nvo vxlan vtep-ip-global 10.255.0.11
nvo vxlan irb
commit
!
! --- EVPN multihoming ---
evpn vxlan multihoming enable
!
interface po10
 description server-multihomed
 evpn multi-homed system-mac 0000.0000.1111
!
! access port mapping: trunk po10 carries vlan 10
interface po10
 access-if-evpn
  map vpn-id 10010
!
! --- L2: mac vrf + VNI 10010 for vlan 10 ---
mac vrf vrf_vl10
 evpn-vlan-service vlan-based
 rd 10.255.0.11:10
 route-target both 65000:10
commit
!
vlan database
 vlan 10 bridge 1 state enable
commit
!
nvo vxlan id 10010 ingress-replication bridge-vlan 10
 vxlan host-reachability-protocol evpn-bgp vrf_vl10
commit
!
! --- L3: ip vrf with L3VNI + IRB anycast gw ---
ip vrf TENANT
 rd 10.255.0.11:100
 route-target both 65000:100
 l3vni 20100
commit
!
interface irb10100
 ip vrf forwarding TENANT
 ip address 192.0.2.1/24
commit
!
nvo vxlan id 10100 ingress-replication
 vxlan host-reachability-protocol evpn-bgp vrf_vl10
 evpn irb10100
commit
!
! --- BGP: underlay to spines + EVPN AF ---
router bgp 65000
 bgp router-id 10.255.0.11
 neighbor 10.255.0.1 remote-as 65000
 neighbor 10.255.0.1 update-source loopback0
 neighbor 10.255.0.2 remote-as 65000
 neighbor 10.255.0.2 update-source loopback0
 address-family l2vpn evpn
  neighbor 10.255.0.1 activate
  neighbor 10.255.0.2 activate
 exit-address-family
 address-family ipv4
  network 10.255.0.11 mask 255.255.255.255
 exit-address-family
commit
end
```

## leaf-2

Symmetric to leaf-1 with these differences:

- `lo0`: 10.255.0.12/32
- `xe3` (to-spine-1): 10.0.0.14/30 ; `xe4` (to-spine-2): 10.0.0.6/30
- `mac vrf vrf_vl10`: `rd 10.255.0.12:10` (RD unique per VTEP, RT identical)
- `ip vrf TENANT`: `rd 10.255.0.12:100`, `l3vni 20100`, `route-target both 65000:100`
- `nvo vxlan vtep-ip-global 10.255.0.12`
- `irb10100`: `ip address 192.0.2.1/24` — same IP on both leaves = anycast gateway
- same `system-mac 0000.0000.1111` on po10 → OcNOS derives ESI from it

## Verification (on leaf-1)

```
show bgp l2vpn evpn summary          ! EVPN sessions to both spines, route counts
show nvo vxlan tunnel                ! tunnel to .12 Installed
show nvo vxlan                       ! VNI 10010/10100, access ports, DF status
show nvo vxlan mac-table             ! local + remote MACs with VTEP/ESI
show nvo vxlan arp-cache             ! IP-MAC bindings
show evpn esi all                    ! both leaves listed for the segment
show evpn l3vni-map                  ! L3VNI 20100 -> TENANT
show evpn irb-status                 ! IRB up
```

End-to-end MAC trace: bgp summary → mac-ip → vni-tunnel → mac-table → esi.

## Notes

- `hardware-profile filter vxlan enable` is required before `nvo vxlan enable`
  on hardware with TCAM groups; on the demo VM it errors and you skip it.
- Binding `evpn irb10100` to the VNI fails with
  `%% L3VNID does not exist` if the IRB is not in an ip vrf that has an l3vni.
- `nvo vxlan irb` must be committed before the ip vrf with l3vni, else
  `%% EVPN-IRB is not Enabled`.
- BUM goes via ingress-replication (no multicast group needed). For multicast
  BUM add `multicast-group <g>` under the VNI instead.
- OcNOS-SP also carries EVPN over MPLS and Type-5 prefix routes for DCI
  between DCs (RFC 9136) — same mac vrf / ip vrf model, different data plane.
- For MPLS L3VPN (non-EVPN) the pattern is: `ip vrf`, `rd`, `route-target`,
  `interface x ip vrf forwarding`, BGP `address-family vpnv4 unicast` with
  `send-community extended` on PE-PE sessions, plus LDP/SR for transport labels.

## References

- IP Infusion blog: VXLAN-EVPN on OcNOS 7.0 (VTEP + MAC learning trace)
- IP Infusion blog: Juniper QFX → OcNOS-DC migration (full leaf config)
- docs.ipinfusion.com — OcNOS VXLAN command reference
- RFC 7432 (EVPN), RFC 8365 (EVPN VXLAN), RFC 9135 (IRB), RFC 9136 (Type-5)
