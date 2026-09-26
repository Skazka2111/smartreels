from smart_reels.process import _concise_process_error


def test_long_ffmpeg_filter_is_truncated_to_readable_error():
    huge_filter = "crop=x='" + "if(lt(t,1),100," * 700 + ")" * 700
    detail = huge_filter + "\nError while processing the decoded data\nConversion failed!"
    result = _concise_process_error(detail)
    assert len(result) < 1800
    assert "Error while processing" in result
    assert "Conversion failed" in result
    assert "crop=x=" not in result
