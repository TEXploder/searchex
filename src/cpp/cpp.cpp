#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <fstream>
#include <string>
#include <vector>
#include <filesystem>
#include <regex>
#include <algorithm>

namespace py = pybind11;
namespace fs = std::filesystem;

static inline unsigned char to_lower_ascii(unsigned char c) {
    return (c >= 'A' && c <= 'Z') ? static_cast<unsigned char>(c + 32) : c;
}
static inline bool is_word_char(unsigned char c) { return std::isalnum(c) || c == '_'; }

static bool is_binary_sample(const std::string& buf) {
    size_t n = std::min<size_t>(buf.size(), 4096);
    if (n == 0) return false;
    size_t suspicious = 0;
    for (size_t i = 0; i < n; ++i) {
        unsigned char c = static_cast<unsigned char>(buf[i]);
        if (c == 0) return true;
        if ((c < 9) || (c > 13 && c < 32)) ++suspicious;
    }
    return (static_cast<double>(suspicious) / n) > 0.30;
}

static std::vector<uint64_t> find_all_substrings(const std::string& data,
                                                 const std::string& pat,
                                                 bool case_sensitive,
                                                 bool whole_word) {
    std::vector<uint64_t> out;
    if (pat.empty() || data.empty()) return out;
    auto it = data.begin();
    while (true) {
        auto found = std::search(it, data.end(),
                                 pat.begin(), pat.end(),
                                 [&](char a, char b) {
                                     if (case_sensitive) return a == b;
                                     return to_lower_ascii((unsigned char)a) == to_lower_ascii((unsigned char)b);
                                 });
        if (found == data.end()) break;
        size_t pos = static_cast<size_t>(found - data.begin());
        bool ok = true;
        if (whole_word) {
            bool left_ok = (pos == 0) || !is_word_char((unsigned char)data[pos - 1]);
            size_t r = pos + pat.size();
            bool right_ok = (r >= data.size()) || !is_word_char((unsigned char)data[r]);
            ok = left_ok && right_ok;
        }
        if (ok) out.push_back(static_cast<uint64_t>(pos));
        it = found + 1;
    }
    return out;
}

static std::vector<uint64_t> find_all_regex(const std::string& data,
                                            const std::string& pattern,
                                            bool case_sensitive) {
    std::vector<uint64_t> out;
    try {
        auto flags = std::regex::ECMAScript;
        if (!case_sensitive) flags = static_cast<std::regex_constants::syntax_option_type>(flags | std::regex::icase);
        std::regex re(pattern, flags);
        auto begin = data.cbegin();
        auto end   = data.cend();
        std::match_results<std::string::const_iterator> match;
        while (std::regex_search(begin, end, match, re)) {
            out.push_back(static_cast<uint64_t>(match.position(0) + (begin - data.cbegin())));
            begin = match.suffix().first;
        }
    } catch (...) { /* invalid regex -> no hits */ }
    return out;
}

static std::vector<size_t> build_newline_index(const std::string& data) {
    std::vector<size_t> nl;
    nl.reserve(data.size() / 64 + 1);
    for (size_t i = 0; i < data.size(); ++i)
        if (data[i] == '\n') nl.push_back(i);
    return nl;
}

static std::vector<uint64_t> positions_to_lines(const std::vector<uint64_t>& pos,
                                                const std::vector<size_t>& nl) {
    std::vector<uint64_t> out; out.reserve(pos.size());
    for (auto p : pos) {
        size_t idx = std::upper_bound(nl.begin(), nl.end(), static_cast<size_t>(p)) - nl.begin();
        out.push_back(static_cast<uint64_t>(idx + 1)); // 1-based line number
    }
    return out;
}

py::dict search_in_file(const std::string& path,
                        const std::vector<std::string>& patterns,
                        bool case_sensitive,
                        bool use_regex,
                        bool whole_word,
                        uint64_t max_bytes /* 0 = unlim */) {
    py::dict result;
    result["path"] = path;
    result["error"] = py::none();
    result["is_binary"] = false;
    result["file_size"] = py::int_(0);

    try {
        fs::path p(path);
        if (!fs::exists(p) || !fs::is_regular_file(p)) {
            result["error"] = std::string("Not found or not a regular file");
            return result;
        }

        uint64_t size = static_cast<uint64_t>(fs::file_size(p));
        result["file_size"] = py::int_(size);
        if (max_bytes > 0 && size > max_bytes) {
            result["error"] = std::string("Skipped: file size > limit");
            return result;
        }

        // ---- Heavy part: release the GIL to keep UI responsive
        py::gil_scoped_release release;

        std::ifstream f(p, std::ios::binary);
        if (!f) {
            py::gil_scoped_acquire acq; // reacquire for Python assignment
            result["error"] = std::string("Failed to open file");
            return result;
        }

        std::string data;
        data.resize(static_cast<size_t>(size));
        if (size > 0) {
            f.read(reinterpret_cast<char*>(&data[0]), static_cast<std::streamsize>(size));
            if (!f) {
                py::gil_scoped_acquire acq;
                result["error"] = std::string("Read error");
                return result;
            }
        }

        bool is_bin = is_binary_sample(data);
        auto nl_index = build_newline_index(data);

        // Acquire GIL to build Python objects
        py::gil_scoped_acquire acq;

        result["is_binary"] = is_bin;
        py::list allhits;
        for (const auto& pat : patterns) {
            std::vector<uint64_t> pos = use_regex
                ? find_all_regex(data, pat, case_sensitive)
                : find_all_substrings(data, pat, case_sensitive, whole_word);
            std::vector<uint64_t> lines = positions_to_lines(pos, nl_index);

            py::dict entry;
            entry["pattern"] = pat;
            entry["positions"] = pos;
            entry["lines"] = lines;
            allhits.append(entry);
        }
        result["hits"] = allhits;
    } catch (const std::exception& ex) {
        result["error"] = std::string("Exception: ") + ex.what();
    } catch (...) {
        result["error"] = std::string("Unknown error");
    }
    return result;
}

PYBIND11_MODULE(searchex_native, m) {
    m.doc() = "C++ search (pybind11) for searchex";
    m.def("search_in_file", &search_in_file,
          py::arg("path"),
          py::arg("patterns"),
          py::arg("case_sensitive") = false,
          py::arg("use_regex") = false,
          py::arg("whole_word") = false,
          py::arg("max_bytes") = 0ULL,
          R"pbdoc(
              Search a file for multiple patterns.
              Returns: dict(path, is_binary, file_size, error, hits=[{pattern, positions, lines}])
          )pbdoc");
}
