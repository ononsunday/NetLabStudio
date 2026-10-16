import ipaddress

import pytest

from netlab.core.subnet import analyze_network, conflicts, convert_number, mask_to_prefix, vlsm_plan


def test_ipv4_binary_and_host_range():
    result = analyze_network("192.168.10.37/24")
    assert result["network"] == "192.168.10.0"
    assert result["broadcast"] == "192.168.10.255"
    assert result["first_host"] == "192.168.10.1"
    assert result["last_host"] == "192.168.10.254"
    assert result["usable_hosts"] == 254
    address = int(result["binary_steps"][0]["value"].replace(" ", ""), 2)
    mask = int(result["binary_steps"][1]["value"].replace(" ", ""), 2)
    assert address & mask == int(ipaddress.ip_address(result["network"]))


@pytest.mark.parametrize("cidr,count,first,last", [
    ("192.0.2.0/31", 2, "192.0.2.0", "192.0.2.1"),
    ("192.0.2.4/32", 1, "192.0.2.4", "192.0.2.4"),
])
def test_point_to_point_and_host_prefix(cidr, count, first, last):
    result = analyze_network(cidr)
    assert (result["usable_hosts"], result["first_host"], result["last_host"]) == (count, first, last)


def test_ipv6_no_broadcast_and_large_range_without_enumeration():
    result = analyze_network("2001:db8:1234::abcd/64")
    assert result["broadcast"] is None
    assert result["network"] == "2001:db8:1234::"
    assert result["num_addresses"] == 2 ** 64
    assert result["last_host"] == "2001:db8:1234:0:ffff:ffff:ffff:ffff"


def test_vlsm_alignment_and_capacity():
    results = vlsm_plan("192.168.1.0/24", [12, 60, 30])
    assert [row["cidr"] for row in results] == ["192.168.1.0/26", "192.168.1.64/27", "192.168.1.96/28"]
    for i, a in enumerate(results):
        for b in results[i + 1:]:
            assert not ipaddress.ip_network(a["cidr"]).overlaps(ipaddress.ip_network(b["cidr"]))
    with pytest.raises(ValueError):
        vlsm_plan("192.168.1.0/30", [5])
    with pytest.raises(ValueError):
        vlsm_plan("192.168.1.0/24", [0])


def test_mask_conflict_and_numeric_conversion():
    assert mask_to_prefix("255.255.240.0") == 20
    result = conflicts(["192.168.1.10/24", "192.168.1.10/25", "2001:db8::1/64"])
    assert len(result["duplicate_addresses"]) == 1
    assert len(result["overlapping_networks"]) == 1
    assert convert_number("-1", 10, 8)["binary"] == "11111111"
    assert convert_number("FF", 16, 8)["signed"] == -1


@pytest.mark.parametrize("bad", ["192.168.1.256/24", "2001:db8:::1/64", "10.1.1.1/33", "bad"])
def test_invalid_address_rejected(bad):
    with pytest.raises(ValueError):
        analyze_network(bad)
