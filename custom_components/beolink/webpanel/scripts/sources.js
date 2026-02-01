"use strict";
angular.module("simpleApp").service("BlSourceCtrl", ["Command", function(a) {
    return {
        create: function(b) {
            var c = {};
            return b && b.id && (c.resource = b.resource,
            a.addMand(c, "Beo4 command", {
                argFun: function(a) {
                    if (_.isObject(a))
                        return a;
                    var c = "Audio_source";
                    return 1 == b.destination ? c = "Video_source" : 254 == b.destination && (c = "V.TAPE/V.MEM"),
                    {
                        Command: a,
                        "Destination selector": c
                    }
                }
            }),
            c.resource = b.resource,
            a.addMand(c, "Beo4 advanced command", {
                argFun: function(a) {
                    if (_.isObject(a))
                        return a;
                    var c = b.link ? "Local_Default_source" : "Remote_source_(main_room)"
                      , d = "Audio_source";
                    return 1 == b.destination ? d = "Video_source" : 254 == b.destination && (d = "V.TAPE/V.MEM"),
                    {
                        Command: a,
                        "Destination selector": d,
                        Link: c,
                        "Secondary source": "DEFAULT"
                    }
                }
            }),
            a.addMand(c, "All standby"),
            a.addMand(c, "BeoRemote One command", {
                argFun: function(a) {
                    return _.isObject(a) ? a : {
                        Command: a,
                        Unit: b.autounit
                    }
                }
            }),
            a.addMand(c, "BeoRemote One Source Selection", {
                argFun: function(a) {
                    return _.isObject(a) ? a : {
                        Command: a,
                        Unit: b.autounit
                    }
                }
            })),
            c
        }
    }
}
]);
var sourcesDefinition = [{
    id: "F0:128",
    label: "TV",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:129",
    label: "RADIO",
    isTv: !1,
    isMusic: !0
}, {
    id: "F0:130",
    label: "DTV2",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:131",
    label: "A.AUX",
    isTv: !1,
    isMusic: !0
}, {
    id: "F0:132",
    label: "MEDIA",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:133",
    label: "V.MEM",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:134",
    label: "DVD",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:135",
    label: "CAMERA",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:138",
    label: "DTV",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:139",
    label: "PC",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:140",
    label: "WEB",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141",
    label: "V.AUX2",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+0+1",
    label: "MATRIX input 01",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+0+2",
    label: "MATRIX input 02",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+0+3",
    label: "MATRIX input 03",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+0+4",
    label: "MATRIX input 04",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+0+5",
    label: "MATRIX input 05",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+0+6",
    label: "MATRIX input 06",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+0+7",
    label: "MATRIX input 07",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+0+8",
    label: "MATRIX input 08",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+0+9",
    label: "MATRIX input 09",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+1",
    label: "MATRIX input 1",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+1+0",
    label: "MATRIX input 10",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+1+1",
    label: "MATRIX input 11",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+1+2",
    label: "MATRIX input 12",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+1+3",
    label: "MATRIX input 13",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+1+4",
    label: "MATRIX input 14",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+1+5",
    label: "MATRIX input 15",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+1+6",
    label: "MATRIX input 16",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+1+7",
    label: "MATRIX input 17",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+1+8",
    label: "MATRIX input 18",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+1+9",
    label: "MATRIX input 19",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+2",
    label: "MATRIX input 2",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+2+0",
    label: "MATRIX input 20",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+2+1",
    label: "MATRIX input 21",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+2+2",
    label: "MATRIX input 22",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+2+3",
    label: "MATRIX input 23",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+2+4",
    label: "MATRIX input 24",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+2+5",
    label: "MATRIX input 25",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+2+6",
    label: "MATRIX input 26",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+2+7",
    label: "MATRIX input 27",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+2+8",
    label: "MATRIX input 28",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+2+9",
    label: "MATRIX input 29",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+3",
    label: "MATRIX input 3",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+3+0",
    label: "MATRIX input 30",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+3+1",
    label: "MATRIX input 31",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+3+2",
    label: "MATRIX input 32",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+4",
    label: "MATRIX input 4",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+5",
    label: "MATRIX input 5",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+6",
    label: "MATRIX input 6",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+7",
    label: "MATRIX input 7",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+8",
    label: "MATRIX input 8",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:141+9",
    label: "MATRIX input 9",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:142",
    label: "PHOTO",
    isTv: !0,
    isMusic: !1
}, {
    id: "F0:144",
    label: "USB2",
    isTv: !1,
    isMusic: !0
}, {
    id: "F0:145",
    label: "A.MEM",
    isTv: !1,
    isMusic: !0
}, {
    id: "F0:146",
    label: "CD",
    isTv: !1,
    isMusic: !0
}, {
    id: "F0:147",
    label: "N.RADIO",
    isTv: !1,
    isMusic: !0
}, {
    id: "F0:148",
    label: "N.MUSIC",
    isTv: !1,
    isMusic: !0
}, {
    id: "F0:148+1",
    label: "Spotify playback",
    isTv: !1,
    isMusic: !0
}, {
    id: "F0:148+2",
    label: "DLNA DMR playback",
    isTv: !1,
    isMusic: !0
}, {
    id: "F0:148+3",
    label: "Q-Play playback",
    isTv: !1,
    isMusic: !0
}, {
    id: "F0:148+4",
    label: "A.AUX playback",
    isTv: !1,
    isMusic: !0
}, {
    id: "F0:149",
    label: "SERVER",
    isTv: !1,
    isMusic: !0
}, {
    id: "F0:150",
    label: "NET",
    isTv: !1,
    isMusic: !0
}, {
    id: "F0:151",
    label: "JOIN",
    isTv: !0,
    isMusic: !0
}, {
    id: "F1:255",
    label: "DVD2",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:0:128",
    label: "TV (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:0:129",
    label: "RADIO (BeoRemote One)",
    isTv: !1,
    isMusic: !0
}, {
    id: "F20:0:130",
    label: "AV IN (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:0:131",
    label: "LINE IN (BeoRemote One)",
    isTv: !1,
    isMusic: !0
}, {
    id: "F20:0:132",
    label: "HOMEMEDIA (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:0:133",
    label: "RECORDINGS (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:0:135",
    label: "CAMERA (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:0:140",
    label: "WEBMEDIA (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:0:144",
    label: "USB (BeoRemote One)",
    isTv: !1,
    isMusic: !0
}, {
    id: "F20:0:145",
    label: "A.MEM (BeoRemote One)",
    isTv: !1,
    isMusic: !0
}, {
    id: "F20:0:146",
    label: "CD (BeoRemote One)",
    isTv: !1,
    isMusic: !0
}, {
    id: "F20:0:147",
    label: "NET RADIO (BeoRemote One)",
    isTv: !1,
    isMusic: !0
}, {
    id: "F20:0:148",
    label: "MUSIC (BeoRemote One)",
    isTv: !1,
    isMusic: !0
}, {
    id: "F20:0:150",
    label: "SPOTIFY (BeoRemote One)",
    isTv: !1,
    isMusic: !0
}, {
    id: "F20:0:151",
    label: "JOIN (toggle) (BeoRemote One)",
    isTv: !0,
    isMusic: !0
}, {
    id: "F20:0:206",
    label: "HDMI 1 (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:0:207",
    label: "MATRIX 1 (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:0:208",
    label: "MATRIX 9 (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:0:209",
    label: "PERSONAL 1 (BeoRemote One)",
    isTv: !0,
    isMusic: !0
}, {
    id: "F20:0:210",
    label: "TV ON (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:0:211",
    label: "MUSIC ON (BeoRemote One)",
    isTv: !1,
    isMusic: !0
}, {
    id: "F20:1:129",
    label: "TUNEIN (BeoRemote One)",
    isTv: !1,
    isMusic: !0
}, {
    id: "F20:1:131",
    label: "A.AUX (BeoRemote One)",
    isTv: !1,
    isMusic: !0
}, {
    id: "F20:1:132",
    label: "DLNA-DMR (BeoRemote One)",
    isTv: !0,
    isMusic: !0
}, {
    id: "F20:1:140",
    label: "YOUTUBE (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:1:144",
    label: "USB 2 (BeoRemote One)",
    isTv: !1,
    isMusic: !0
}, {
    id: "F20:1:150",
    label: "DEEZER (BeoRemote One)",
    isTv: !1,
    isMusic: !0
}, {
    id: "F20:1:206",
    label: "HDMI 2 (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:1:207",
    label: "MATRIX 2 (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:1:208",
    label: "MATRIX 10 (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:1:209",
    label: "PERSONAL 2 (BeoRemote One)",
    isTv: !0,
    isMusic: !0
}, {
    id: "F20:1:211",
    label: "PATTERNPLAY (BeoRemote One)",
    isTv: !1,
    isMusic: !0
}, {
    id: "F20:2:129",
    label: "DVB RADIO (BeoRemote One)",
    isTv: !1,
    isMusic: !0
}, {
    id: "F20:2:131",
    label: "BLUETOOTH (BeoRemote One)",
    isTv: !1,
    isMusic: !0
}, {
    id: "F20:2:148",
    label: "AirPlay (BeoRemote One)",
    isTv: !0,
    isMusic: !0
}, {
    id: "F20:2:150",
    label: "QPLAY (BeoRemote One)",
    isTv: !1,
    isMusic: !0
}, {
    id: "F20:2:206",
    label: "HDMI 3 (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:2:207",
    label: "MATRIX 3 (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:2:208",
    label: "MATRIX 11 (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:2:209",
    label: "PERSONAL 3 (BeoRemote One)",
    isTv: !0,
    isMusic: !0
}, {
    id: "F20:3:206",
    label: "HDMI 4 (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:3:207",
    label: "MATRIX 4 (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:3:208",
    label: "MATRIX 12 (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:3:209",
    label: "PERSONAL 4 (BeoRemote One)",
    isTv: !0,
    isMusic: !0
}, {
    id: "F20:4:206",
    label: "HDMI 5 (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:4:207",
    label: "MATRIX 5 (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:4:208",
    label: "MATRIX 13 (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:4:209",
    label: "PERSONAL 5 (BeoRemote One)",
    isTv: !0,
    isMusic: !0
}, {
    id: "F20:5:206",
    label: "HDMI 6 (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:5:207",
    label: "MATRIX 6 (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:5:208",
    label: "MATRIX 14 (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:5:209",
    label: "PERSONAL 6 (BeoRemote One)",
    isTv: !0,
    isMusic: !0
}, {
    id: "F20:6:206",
    label: "HDMI 7 (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:6:207",
    label: "MATRIX 7 (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:6:208",
    label: "MATRIX 15 (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:6:209",
    label: "PERSONAL 7 (BeoRemote One)",
    isTv: !0,
    isMusic: !0
}, {
    id: "F20:7:206",
    label: "HDMI 8 (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:7:207",
    label: "MATRIX 8 (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:7:208",
    label: "MATRIX 16 (BeoRemote One)",
    isTv: !0,
    isMusic: !1
}, {
    id: "F20:7:209",
    label: "PERSONAL 8 (BeoRemote One)",
    isTv: !0,
    isMusic: !0
}];
angular.module("simpleApp").filter("sourceFilter", function() {
    return function(a, b) {
        return a && a.length > 0 && angular.isDefined(b) ? a.filter(function(a, c, d) {
            var e = _.find(sourcesDefinition, {
                id: a.source
            });
            return !a.hidden && (!angular.isDefined(e) || e[b])
        }) : a
    }
}),
angular.module("simpleApp").directive("avControl", ["$rootScope", "BlSourceCtrl", "$filter", function(a, b, c) {
    return {
        templateUrl: "components/avcontrol/avControl.html",
        scope: {
            sources: "=avControl"
        },
        compile: function(d, e) {
            return function(d, e, f) {
                function g() {
                    angular.forEach(d.sources, function(a) {
                        if (_.isEmpty(a.name)) {
                            var b = _.find(sourcesDefinition, {
                                id: a.source
                            });
                            b && b.label && b.label.length > 0 ? a.name = b.label : a.name = "unnamed"
                        }
                    }),
                    d.tvSources = c("sourceFilter")(d.sources, "isTv"),
                    d.musicSources = c("sourceFilter")(d.sources, "isMusic")
                }
                function h() {
                    g();
                    var b = d.selected && d.selected.id;
                    d.selected && d.selected.id && (d.selected = _.find(d.sources, {
                        id: d.selected.id
                    })),
                    !d.selected && a.lastSelectedSourceId && (d.selected = _.find(d.sources, {
                        id: a.lastSelectedSourceId
                    })),
                    !d.selected && d.sources && d.sources.length > 0 ? d.selected = d.sources[0] : d.selected = null,
                    d.selected && d.selected.id !== b && (a.lastSelectedSourceId = d.selected.id)
                }
                d.selected = null,
                d.showSources = !1,
                d.tvSources = [],
                d.musicSources = [],
                d.select = function(a) {
                    d.selected = a;
                    var c = b.create(a);
                    d.showSources = !1,
                    angular.forEach(a.selectionCommands, function(a) {
                        var b = a.substring(a.indexOf("?"), -1).split(" ").join("_")
                          , d = queryToParams(a);
                        c[b](d)
                    })
                }
                ,
                h();
                var i = a.$on("model:updated", function(a, b) {
                    (!b || b && b.backend && "BlSources" == b.backend) && h()
                });
                d.$watchCollection("sources", h),
                d.$on("$destroy", i)
            }
        }
    }
}
]),
function() {
    var a = ["$scope", "BlSourceCtrl", function(a, b) {
        function c() {
            a.source && a.source.id && a.source.id !== d && (a.selectedCtrl = b.create(a.source),
            d = a.source.id)
        }
        var d;
        a.selectedCtrl = {},
        a.showAllStandby = !1,
        a.exec = function(b) {
            a.selectedCtrl && angular.isDefined(a.selectedCtrl.Beo4_command) ? (a.selectedCtrl.Beo4_command(b),
            a.showAllStandby = !1) : console.log("ups, Beo4_advanced_command not defined for current source")
        }
        ,
        a.standby = function() {
            a.showAllStandby ? (a.selectedCtrl.All_standby(),
            a.showAllStandby = !1) : (a.exec("STANDBY"),
            a.showAllStandby = !0)
        }
        ,
        a.$watch("source", c),
        a.$on("$destroy", function() {})
    }
    ];
    angular.module("simpleApp").directive("srcControl", [function() {
        return {
            templateUrl: "components/avcontrol/srcControl.html",
            restrict: "A",
            scope: {
                source: "=srcControl"
            },
            controller: a
        }
    }
    ]),
    angular.module("simpleApp").directive("srcQuickControl", [function() {
        return {
            templateUrl: "components/avcontrol/srcQuickControl.html",
            restrict: "A",
            scope: {
                source: "=srcQuickControl"
            },
            controller: a
        }
    }
    ])
}();
