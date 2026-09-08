import json
from unittest import mock

from src.collectors import disks


def _node():
    return {
        "name": "sda",
        "kname": "sda",
        "type": "disk",
        "size": "500107862016",
        "model": "Samsung SSD 850 EVO",
        "vendor": "ATA",
        "serial": "S3ZBNX0J123456",
        "fstype": None,
        "mountpoint": None,
        "rota": "0",
        "tran": "sata",
        "rm": "0",
        "pttype": "gpt",
        "children": [],
    }


def test_disk_type_label():
    assert disks.disk_type_label(True, "sata", "sda") == "HDD"
    assert disks.disk_type_label(False, "sata", "sda") == "SSD"
    assert disks.disk_type_label(False, "nvme", "nvme0n1") == "NVMe SSD"
    assert disks.disk_type_label(None, "usb", "sdb") == "Desconocido"


def test_build_partition():
    node = {
        "name": "sda1",
        "size": "524288000",
        "fstype": "vfat",
        "mountpoint": "/boot/efi",
    }

    partition = disks.build_partition(node)

    assert partition["device"] == "/dev/sda1"
    assert partition["size_bytes"] == 524288000
    assert partition["size_gb"] == round(524288000 / (1024 ** 3), 2)
    assert partition["size_human"] == "500.0 MB"
    assert partition["filesystem"] == "vfat"
    assert partition["mountpoint"] == "/boot/efi"


def test_build_disk():
    disk = disks.build_disk(_node())

    assert disk["device"] == "/dev/sda"
    assert disk["model"] == "Samsung SSD 850 EVO"
    assert disk["vendor"] == "ATA"
    assert disk["serial"] == "S3ZBNX0J123456"
    assert disk["transport"] == "sata"
    assert disk["rotational"] is False
    assert disk["removable"] is False
    assert disk["partition_table"] == "gpt"
    assert disk["type"] == "SSD"
    assert disk["size_bytes"] == 500107862016
    assert disk["size_gb"] == round(500107862016 / (1024 ** 3), 2)
    assert disk["partitions"] == []


@mock.patch("src.collectors.disks.get_lsblk")
def test_parse_disks_uses_lsblk(mock_get_lsblk, lsblk_sample):
    mock_get_lsblk.return_value = lsblk_sample["blockdevices"]

    result = disks.parse_disks([], {})

    assert len(result) == 2

    first = result[0]
    assert first["model"] == "Samsung SSD 850 EVO"
    assert first["type"] == "SSD"
    assert len(first["partitions"]) == 2
    assert first["partitions"][0]["mountpoint"] == "/boot/efi"

    second = result[1]
    assert second["model"] == "Samsung SSD 970 EVO Plus 1TB"
    assert second["type"] == "NVMe SSD"
    assert second["size_gb"] == round(1000204886016 / (1024 ** 3), 2)


@mock.patch("src.collectors.disks.get_lsblk")
def test_parse_disks_empty_when_no_lsblk(mock_get_lsblk):
    mock_get_lsblk.return_value = []

    result = disks.parse_disks([], {})

    assert result == []